import yaml

import dedupe
import dedupe_variable_name
import psycopg2
import psycopg2.extras

config_location = 'config.yml'
settings_location = 'dedupe.settings'

with open(config_location, 'r') as config_file:
    config = yaml.load(config_file.read())

c1 = psycopg2.connect(
    database = config["db"]["database"],
    cursor_factory = psycopg2.extras.RealDictCursor)

c2 = psycopg2.connect(
    database = config["db"]["database"],
    cursor_factor = psycopg2.extras.RealDictCursor)

cursor = c1.cursor()

if os.path.exists(settings_location):
    with open(settings_location, 'r') as settings:
        linker = dedupe.StaticGazetteer(settings, num_cores = 2)
else:
    # Best way to link two datasets with different fields?
    fields = [{ 'field': 'Address', 'type': 'Address' }]
    
    linker = dedupe.Gazetteer(fields, num_cores = 2)

    dedupe.consoleLabel(linker)

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




