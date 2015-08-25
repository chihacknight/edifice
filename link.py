# Link Chicago Building Footprints to  Cook County Address Points using dedupe

# This script is cobbled together out of several example scripts by DataMade:
#   https://github.com/datamade/address-matching/blob/master/address_matching.py
#   https://github.com/datamade/dedupe-examples/blob/master/pgsql_big_dedupe_example/pgsql_big_dedupe_example.py
#   https://github.com/datamade/dedupe-geocoder

import csv
import os
import logging

import dedupe
import dedupe.variables.address
import psycopg2
import psycopg2.extras

settings_location = 'dedupe.settings'
training_location = 'address_matching_training.json'

block_map_location = '%s_block_map.csv'
match_map_location = 'match_map.csv'

conn = psycopg2.connect( 
    database = os.environ['PGDATABASE']
    , user = os.environ['PGUSER']
    , cursor_factory = psycopg2.extras.RealDictCursor
    )

cursor = conn.cursor()

datasets = {
    "canonical": "addresses",
    "messy": "buildings"
}

# Transform the row into the format expected by dedupe.
def dedupe_format(row):
    row['latlng'] = (row['lat'], row['lng'])
    return row

# Both canonical and messy datasets are expected to have these columns
get_data = \
    """
    SELECT
        CAST (ST_X(latlng) AS double precision) AS lng,
        CAST (ST_Y(latlng) AS double precision) AS lat,
        address,
        gid
    FROM %s
    """

if os.path.exists(settings_location):
    with open(settings_location, 'r') as settings:
        linker = dedupe.StaticGazetteer(settings, num_cores = 2)
else:
    fields = [
        {
            'field': 'address',
            'type': 'Address',
            'has missing': True,
            'variable name': 'address'
        },
        {
            'field': 'latlng',
            'type': 'LatLong',
            'has missing': True,
            'variable name': 'latlng'
        },
        {
            'type': 'Interaction',
            'interaction variables': ['address', 'latlng']
        }
    ]

    linker = dedupe.Gazetteer(fields, num_cores = 2)

    sampling_data = {}

    for role, table_name in datasets.iteritems():
        sampling_cursor = conn.cursor('%s_select' % table_name)
        sampling_cursor.execute(get_data % table_name)

        sampling_data[role] = dict(
            (i, dedupe_format(row)) for i, row in enumerate(sampling_cursor)
        )

    logging.info('sampling')
    linker.sample(sampling_data["canonical"], sampling_data["messy"], 75000)
    del sampling_data

    # Use training data from previous runs of dedupe, if it exists.
    # Note: If you want to retrain from scratch, delete the training data file.
    if os.path.exists(training_location):
        logging.info('reading labeled examples from %s', training_location)
        with open(training_location, 'r') as training:
            linker.readTraining(training)

    logging.info('starting interactive labeling')
    dedupe.consoleLabel(linker)

    logging.info('training model')
    linker.train(ppc = 0.1, uncovered_dupes = 5, index_predicates = False)

    # when finished, save our training away to disk
    with open(training_location, 'w') as training:
        linker.writeTraining(training)

    with open(settings_location, 'w') as settings:
        linker.writeSettings(settings)

    linker.cleanupTraining()

#logging.info('indexing')
# If dedupe learned a predicate which requires indexing the data, we must
# take a pass through the data and create indices.
# dedupe allows index predicates by default during sampling and training.
#for field in deduper.blocker.index_fields:
#    for role, table_name in datasets.iteritems():
#        indexing_cursor = conn.cursor('indexing_cursor')
#        indexing_cursor.execute(
#            """
#            SELECT DISTINCT {field} FROM {table} 
#            """
#        ).format(field = field, table = table_name)
#        field_data = (row[field] for dedupe_format(row) in indexing_cursor)
#        deduper.blocker.index(field_data, field)
#        indexing_cursor.close()

logging.info('blocking')

# To run blocking on such a large set of data, we create a separate table
# for each dataset containing block keys and record ids
for role, table_name in datasets.iteritems():
    logging.info('blocking %s dataset', table_name)

    cursor.execute("CREATE TABLE %s_block_map \
        (block_key VARCHAR(200), gid INTEGER)" % table_name)

    blocking_cursor = conn.cursor('%s_blocking_cursor' % table_name)
    blocking_cursor.execute(get_data % table_name)

    full_data = ((row['gid'], dedupe_format(row)) for row in blocking_cursor)
    blocked_data = linker.blocker(full_data)

    # Write blocking map to CSV so we can quickly load it in with Postgres COPY
    with open(block_map_location % table_name, 'w') as block_map_csv:
        block_map_writer = csv.writer(block_map_csv)
        block_map_writer.writerows(blocked_data)
        blocking_cursor.close()

    # Populate block map table
    with open(block_map_location % table_name, 'r') as block_map_csv:
        cursor.copy_expert(
            "COPY %s_block_map FROM STDIN CSV" % table_name,
            block_map_csv
        )

    conn.commit()

    logging.info('indexing block_key for %s', table_name)
    cursor.execute(
        """
        CREATE INDEX {0}_block_map_key_idx
        ON {0}_block_map (block_key)
        """.format(table_name)
    )

logging.info('matching messy dataset')
def block_data():
    get_messy_blocks = \
        """
        SELECT
            blocks.gid AS blocked_record_id,
            array_agg(blocks.block_key) AS block_keys,
            MAX(messy_data.address) AS address
        FROM {messy}_block_map AS blocks
        JOIN {messy} AS messy_data
            USING (gid)
        GROUP BY gid
        """.format(messy = datasets["messy"])

    get_canonical_blocks = \
        """
        SELECT
            DISTINCT ON ({canonical}.gid)
            {canonical}.gid,
            {canonical}.address
        FROM {canonical}
        JOIN {canonical}_block_map AS blocks
            USING (gid)
        WHERE blocks.block_key IN %s
        ORDER BY {canonical}.gid
        """.format(canonical = datasets["canonical"])

    matching_cursor = conn.cursor('matching_cursor')
    matching_cursor.execute(get_messy_blocks)

    for messy_record in matching_cursor:
        canonical_cursor = conn.cursor('canonical_cursor')

        record = {
            k : v
            for k, v in zip(messy_record.keys(), messy_record.values()) \
            if k not in ['blocked_record_id', 'block_keys']
        }

        a = [(messy_record["blocked_record_id"], record, set())]

        rows = canonical_cursor.execute(
            get_canonical_blocks % str(tuple(messy_record.block_keys))
        )

        b = [(row["gid"], dedupe_format(row), set()) for row in rows]

        if b:
            yield (a, b)

    matching_cursor.close()

blocked_pairs = block_data()
matches = linker.matchBlocks(blocked_pairs)

logging.info('writing csv with matches between buildings and addresses')
with open(match_map_location, 'w') as matches_csv:
    matches_csv_writer = csv.writer(matches_csv)
    for match in matches:
        for link in match:
            (messy_id, canonical_id), confidence = link
            if float(confidence) > 0.8:
                matches_csv_writer.writerow([
                    int(messy_id),
                    int(canonical_id),
                    float(confidence)
                ])

conn.commit()

logging.info('loading match csv into database')
cursor.execute(
    """
    CREATE TABLE match_map (
        messy_id INTEGER,
        canonical_id INTEGER,
        confidence DOUBLE PRECISION
    )
    """
)

with open(match_map_location, 'r') as matches_csv:
    cursor.copy_expert("COPY match_map FROM STDIN CSV", matches_csv)

conn.commit()

logging.info('adding foreign key for address to the buildings table')
cursor.execute(
    """
    UPDATE {messy} SET
        addressid = tmp.addressid,
        match_confidence = tmp.confidence
    FROM (
        SELECT
            {canonical}.addressid,
            match_map.messy_id,
            match_map.confidence
        FROM {canonical}
        JOIN match_map
        ON {canonical}.gid = match_map.canonical_id
    ) AS tmp
    WHERE {messy}.gid = tmp.messy_id
    """.format(canonical = datasets["canonical"], messy = datasets["messy"])
)

