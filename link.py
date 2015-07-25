# Link the Chicago Building Footprints dataset to the Cook County Address Point dataset using dedupe so that the two datasets can be joined on the Cook County PIN.
# This script is cobbled together out of two example scripts by DataMade:
#   https://github.com/datamade/address-matching/blob/master/address_matching.py#   https://github.com/datamade/dedupe-examples/blob/master/pgsql_big_dedupe_example/pgsql_big_dedupe_example.py   

import csv
import os

import dedupe
import dedupe.variables
import psycopg2
import psycopg2.extras

settings_location = 'dedupe.settings'
training_location = 'dedupe_training.json'

conn1 = psycopg2.connect( 
    database = os.environ['PGDATABASE']
    , user = os.environ['PGUSER']
    , cursor_factory = psycopg2.extras.RealDictCursor 
    )

conn2 = psycopg2.connect( 
    database = os.environ['PGDATABASE']
    , user = os.environ['PGUSER']
    , cursor_factory = psycopg2.extras.RealDictCursor
    )

cursor = conn1.cursor()

if os.path.exists(settings_location):
    with open(settings_location, 'r') as settings:
        linker = dedupe.StaticGazetteer(settings, num_cores = 2)
else:

    fields = [ 
        { 
            'field': 'Address', 
            'type': 'Address', 
            'has missing': True,
            'variable name': 'address' 
        },
        { 
            'field': 'LatLng', 
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

    address_select = c1.cursor('address_select')
    address_select.execute("SELECT address FROM addresses")

    tmp_canonical = dict((i, row) for i, row in enumerate(address_select))
    tmp_messy = dict((i, row) for i, row in enumerate(address_select))

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

    # We train dedupe on a random sample of the addresses.
    linker.sample(messy_addresses, canonical_addresses, 30000)
    
    linker.train()

    # when finished, save our training away to disk
    with open(training_location, 'w') as training:
        linker.writeTraining(training)

    with open(settings_location, 'w') as settings:
        linker.writeSettings(settings)

    linker.cleanupTraining()

print 'indexing...'
linker.index(canonical_addresses)

print 'clustering...'
clustered_dupes = linker.match(messy_addresses, 0.0)

print '# duplicate sets', len(clustered_dupes)
print 'out of', len(messy_addresses)

canonical_lookup = {}
for n_results in clustered_dupes:
    (source_id, target_id), score = n_results[0]
    canonical_lookup[source_id] = (target_id, score)




