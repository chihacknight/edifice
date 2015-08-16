# Link the Chicago Building Footprints dataset to the Cook County Address Point dataset using dedupe so that the two datasets can be joined on the Cook County PIN.
# This script is cobbled together out of two example scripts by DataMade:
#   https://github.com/datamade/address-matching/blob/master/address_matching.py#   https://github.com/datamade/dedupe-examples/blob/master/pgsql_big_dedupe_example/pgsql_big_dedupe_example.py   

import csv
import os
import tempfile

import dedupe
import dedupe.variables.address
import psycopg2
import psycopg2.extras

settings_location = 'dedupe.settings'
training_location = 'address_matching_training.json'

conn = psycopg2.connect( 
    database = os.environ['PGDATABASE']
    , user = os.environ['PGUSER']
    , cursor_factory = psycopg2.extras.RealDictCursor 
    )

cursor = conn.cursor()

canonical_select = "SELECT \
    CAST (ST_X(latlng) AS double precision) AS lng, \
    CAST (ST_Y(latlng) AS double precision) AS lat, \
    address, \
    pin \
    FROM addresses"

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

    print 'selecting canonical addresses from addresses database'
    canonical_addresses = conn.cursor('canonical_select')
    canonical_addresses.execute(canonical_select)

    print 'selecting messy addresses from buildings database'
    messy_addresses = conn.cursor('messy_select')
    messy_addresses.execute("SELECT \
        CAST (ST_X(latlng) AS double precision) AS lng, \
        CAST (ST_Y(latlng) AS double precision) AS lat, \
        address \
        FROM buildings"
    )

    # Transform the row into the format expected by dedupe.
    def dedupeFormat(row):
        row['latlng'] = (row['lat'], row['lng'])
        return row

    tmp_canonical = dict(
        (i, dedupeFormat(row)) for i, row in enumerate(canonical_addresses)
    )

    tmp_messy = dict(
        (i, dedupeFormat(row)) for i, row in enumerate(messy_addresses)
    )

    linker.sample(tmp_canonical, tmp_messy, 75000)
    del tmp_canonical, tmp_messy


    # Use training data from previous runs of dedupe, if it exists.
    # Note: If you want to retrain from scratch, delete the training data file.
    if os.path.exists(training_location):
        print 'reading labeled examples from...', training_location
        with open(training_location, 'r') as training:
            linker.readTraining(training)

    print 'starting interactive labeling...'
    dedupe.consoleLabel(linker)

    linker.train(ppc = 0.001, uncovered_dupes = 5)

    # when finished, save our training away to disk
    with open(training_location, 'w') as training:
        linker.writeTraining(training)

    with open(settings_location, 'w') as settings:
        linker.writeSettings(settings)

    linker.cleanupTraining()

print 'blocking...'

print 'creating blocking map database...'
cursor.execute("DROP TABLE IF EXISTS blocking_map")
cursor.execute("CREATE TABLE blocking_map "
    "(block_key VARCHAR(200), pin VARCHAR(17))")

# If dedupe learned an Index Predicate, we have to take a pass through the data
# and create indices.
print 'creating inverted index...'

for field in linker.blocker.index_fields:
    c2 = conn.cursor('c2')
    c2.execute("SELECT DISTINCT %s FROM addresses" % field)
    field_data = set(row[field] for row in c2)
    linker.blocker.index(field_data, field)
    c2.close()

print 'writing blocking map...'

c3 = conn.cursor('address_select2')
c3.execute(canonical_select)
full_data = ((row['pin'], row) for row in c3)
blocked_data = linker.blocker(full_data)

# Write out blocking map to CSV so we can quickly load it in with Postgres COPY
blocking_map_csv = tempfile.NamedTemporaryFile(prefix = 'blocks_', delete = False)
blocking_map_writer = csv.writer(blocking_map_csv)
blocking_map_writer.writerows(blocked_data)
c3.close()
blocking_map_csv.close()

# Populate blocking map table
f = open(blocking_map_csv.name, 'r')
cursor.copy_expert("COPY blocking_map FROM STDIN CSV", f)
f.close()

os.remove(blocking_map_csv.name)

conn.commit()

print 'prepare blocking table. this will probably take a while...'
logging.info('indexing block_key')

cursor.execute("CREATE INDEX blocking_map_key_idx ON blocking_map (block_key)")

cursor.execute("DROP TABLE IF EXISTS plural_key")
cursor.execute("DROP TABLE IF EXISTS plural_block")
cursor.execute("DROP TABLE IF EXISTS covered_blocks")
cursor.execute("DROP TABLE IF EXISTS smaller_coverage")

logging.info('calculating plural key')
cursor.execute("CREATE TABLE plural_key "
    "(block_key VARCHAR(200), "
    " block_id SERIAL PRIMARY KEY)")

cursor.execute("INSERT INTO plural_key (block_key) "
    "SELECT block_key FROM blocking_map "
    "GROUP BY block_key HAVING COUNT(*) > 1")

logging.info('creating block key index')
cursor.execute("CREATE UNIQUE INDEX block_key_idx ON plural_key (block_key)")

logging.info('calculating plural_block')
cursor.execute("CREATE TABLE plural_block "
    "AS (SELECT block_id, pin "
    " FROM blocking_map INNER JOIN plural_key "
    " USING (block_key))")

logging.info('adding pin index and sorting index')
cursor.execute("CREATE INDEX plural_block_pin_idx ON plural_block (pin)")
cursor.execute("CREATE UNIQUE INDEX plural_block_block_id_pin_uniq "
    " ON plural_block (block_id, pin)")

logging.info('creating covered_blocks')
cursor.execute("CREATE TABLE covered_blocks "
    "AS (SELECT donor_id, "
    " string_agg(CAST(block_id AS TEXT), ',' ORDER BY block_id) "
    "  AS sorted_ids "
    " FROM plural_block "
    " GROUP BY pin)")

cursor.execute("CREATE UNIQUE INDEX covered_blocks_pin_idx "
    "ON covered_blocks (pin)")

conn.commit()

logging.info('creating smaller coverage')
cursor.execute("CREATE TABLE smaller_coverage "
    "AS (SELECT pin, block_id, "
    " TRIM(',' FROM split_part(sorted_ids, CAST(block_id AS TEXT), 1)) "
    "  AS smaller_ids "
    " FROM plural_block INNER JOIN covered_blocks "
    " USING (donor_id))")

conn.commit()


# Clustering

def addresses_cluster(results):
    lset = set

    block_id = None
    records = []
    i = 0

    for row in results:
        if row['block_id'] != block_id:
            if records:
                yield records
            else:
                block_id = row['block_id']
                records = []
                i += 1

                if i % 10000 == 0:
                    print i, "blocks"
                    print time.time() - start.time, "seconds"
        else:
            smaller_ids = row['smaller_ids']

            if smaller_ids:
                smaller_ids = lset(smaller_ids.split(','))
            else:
                smaler_ids = lset([])

            records.append((row['pin'], row, smaller_ids))

    if records:
        yield records

c4 = conn.cursor('c4')
c4.execute("SELECT pin, "
    "FROM smaller_coverage "
    "INNER JOIN buildings "
    "USING (pin) "
    "ORDER BY (block_id)")

print 'clustering...'
clustered_dupes = linker.matchBlocks(addresses_cluster(c4), threshold = 0.5)

# Write out results

with open('entity_map.csv', 'w') as entity_map_csv:
    entity_map_writer = csv.writer(entity_map_csv)

    for cluster, scores in clustered_dupes:
        cluster_id = cluster[0]
        for donor_id, score in zip(cluster, scores):
            entity_map_writer.writerow([pin, cluster_id, score])

c4.close()
conn.commit()

print '# duplicate sets', len(clustered_dupes)
print 'out of', len(messy_addresses)

canonical_lookup = {}
for n_results in clustered_dupes:
    (source_id, target_id), score = n_results[0]
    canonical_lookup[source_id] = (target_id, score)

