# Load data from FOIA request into postgres.
# Note that the schema for the foia table was already set up using csvsql from csvkit.
cat FOI22606.CSV | psql sunrooms -c "COPY foia FROM stdin WITH (FORMAT CSV, HEADER true)"

# Load building footprints dataset from the City of Chicago data portal into postgres.
shp2pgsql -D -W "LATIN1" buildings footprints | psql sunrooms