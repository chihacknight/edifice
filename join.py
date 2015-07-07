# Link the Chicago Building Footprints dataset to the Cook County Address Point dataset using dedupe so that the two datasets can be joined on the Cook County PIN.
# This script is cobbled together out of two example scripts by DataMade:
#   https://github.com/datamade/address-matching/blob/master/address_matching.py#   https://github.com/datamade/dedupe-examples/blob/master/pgsql_big_dedupe_example/pgsql_big_dedupe_example.py   

import yaml

import dedupe
import dedupe.variables
import psycopg2
import psycopg2.extras

config_location = 'config.yml'
settings_location = 'dedupe.settings'

with open(config_location, 'r') as config_file:
    config = yaml.load(config_file.read())

c1 = psycopg2.connect( 
    database = config["db"]["database"]
    , cursor_factory = psycopg2.extras.RealDictCursor 
    )

c2 = psycopg2.connect(
    database = config["db"]["database"],
    cursor_factory = psycopg2.extras.RealDictCursor)

#if os.path.exists(settings_location):
#    with open(settings_location, 'r') as settings:
#        linker = dedupe.StaticGazetteer(settings, num_cores = 2)
#else:

#    fields = [{ 'field': 'Address', 'type': 'Address' }]
    
    linker = dedupe.Gazetteer(fields, num_cores = 2)

    address_select = c1.cursor('address_select')
    address_select.execute("SELECT address FROM addresses")

    tmp_canonical = dict((i, row) for i, row in enumerate(address_select))
    tmp_messy = dict((i, row) for i, row in enumerate(address_select))

    linker.sample(tmp_canonical, tmp_messy, 75000)
    del tmp_gazetteer

    # Use training data from previous runs of dedupe, if it exists.
    # Note: If you want to retrain from scratch, delete the training data file.
    if os.path.exists(training_location):
        print 'reading labeled examples from...', training_location
        with open(training_location, 'r') as training:
            linker.readTraining(training)

    print 'starting interactive labeling...'
    dedupe.consoleLabel(linker)

#    # We train dedupe on a random sample of the addresses.
#    linker.sample(messy_addresses, canonical_addresses, 30000))
#    
    
#    dedupe.consoleLabel(linker)
#    linker.train()
#
#    # when finished, save our training away to disk
#    with open(training_location, 'w') as training:
#        linker.writeTraining(training)
#
#    with open(settings_location, 'w') as settings:
#        linker.writeSettings(settings)
#
#    linker.cleanupTraining()

#print 'indexing...'
#linker.index(canonical_addresses)

#print 'clustering...'
#clustered_dupes = linker.match(messy_addresses, 0.0)

#print '# duplicate sets', len(clustered_dupes)
#print 'out of', len(messy_addresses)

#canonical_lookup = {}
#for n_results in clustered_dupes:
#    (source_id, target_id), score = n_results[0]
#    canonical_lookup[source_id] = (target_id, score)




