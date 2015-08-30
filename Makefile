include config.mk

.PHONY : all
all : edifice.table


.PHONY: clean
clean : $(PGDATABASE).clean
	# Clean up downloaded files
	# Use `rm -f` so that no errors are thrown if the files don't exist.
	rm -f *.{dbf,prj,sbn,sbx,shp,shx} # shapefiles
	rm -f *.zip
	rm -f *.sql
	rm -f *.CSV *.csv


.PHONY : download
download : buildings.zip addresses.zip 97634.sql foia-22606-2013-10-16.zip


# Set up python virtualenv and install python dependencies.
bin/activate : requirements.txt
	virtualenv .

	# install numpy first to avoid dependency errors
	source $@; \
		pip install "numpy>=1.9"; \
		pip install -r $<


# Set target-specific TABLE variable for each target which modifies a db table.
%.table : TABLE = $(basename $@)


# =================
# Combined datasets
# =================

# Match addresses and buildings using dedupe.
edifice.table : link.py bin/activate addresses.table buildings.table taxes.table
	source bin/activate; python $<
	
	psql -c "CREATE TABLE $(TABLE) AS \
		 SELECT \
			a.address, \
			a.latlng, \
			b.geom AS footprint, \
			b.year_built, \
			b.stories, \
			b.bldg_condi AS building_condition, \
			t.pin, \
			t.property_class, \
			t.tax_code, \
			t.property_class_description, \
			t.current_land AS current_land_value, \
			t.current_building AS current_building_value, \
			t.current_total AS current_total_value, \
			t.current_market_value, \
			t.building_age, \
			t.assessment_year, \
			t.building_use, \
			t.neighborhood, \
			t.exterior_construction	\
		 FROM addresses a \
			INNER JOIN buildings b ON (a.gid = b.address_gid) \
			INNER JOIN taxes t USING (pin)"
		 
	touch $@


# =================================================================
# Cook County Tax Assessor's Data (obtained via FOIA request 22606)
# =================================================================
taxes.table : FOI22606.CSV $(PGDATABASE).db
	psql -c \
		"CREATE TABLE $(TABLE) \
		 (pin CHAR(14), \
		  mailing_address VARCHAR(50), \
		  property_location VARCHAR(50), \
		  township VARCHAR(13), \
		  property_class INTEGER, \
		  property_class_description VARCHAR(150), \
		  triennial VARCHAR(4), \
		  land_square_footage INTEGER, \
		  building_square_footage INTEGER, \
		  neighborhood VARCHAR(3), \
		  tax_code CHAR(5), \
		  current_land INTEGER, \
		  current_building INTEGER, \
		  current_total INTEGER, \
		  current_market_value INTEGER, \
		  prior_land INTEGER, \
		  prior_building INTEGER, \
		  prior_total INTEGER, \
		  prior_market_value INTEGER, \
		  residence_type VARCHAR(25), \
		  building_use VARCHAR(15), \
		  number_of_apartments INTEGER, \
		  exterior_construction VARCHAR(15), \
		  full_baths INTEGER, \
		  half_baths INTEGER, \
		  basement_description VARCHAR(30), \
		  attic_description VARCHAR(25), \
		  fireplaces INTEGER, \
		  garage_description VARCHAR(20), \
		  building_age INTEGER, \
		  pass INTEGER, \
		  assessment_year INTEGER)"
	iconv -f latin1 -t utf-8 $< | \
	psql -c "COPY $(TABLE) FROM STDIN \
		 WITH CSV QUOTE AS '\"' DELIMITER AS ','"
	
	# Index 'pin' to improve performance of join.
	psql -c "CREATE INDEX $(TABLE)_pin_idx ON $(TABLE) (pin)"

	touch $@

FOI22606.CSV : foia-22606-2013-10-16.zip
	unzip -j $< "FOI 22606/$@"
	touch $@

foia-22606-2013-10-16.zip :
	wget --no-use-server-timestamps https://s3.amazonaws.com/purple-giraffe-data/$@


# =========================
# Illinois State Plane SRID
# =========================
97634.insert : 97634.sql $(PGDATABASE).db
	# Chicago Building Footprints dataset has coordinates in the IL State Plane
	# coordinate system (also see Cook County Address Points metadata).
	# Note that PostGIS doesn't accept the ESRI:102671 SRID, so I'm using
	# SR-ORG:7634, which is very similar, instead.
	sudo -u postgres --preserve-env \
		psql -U postgres -f $<
	touch $@

97634.sql :
	wget --no-use-server-timestamps -O $@ \
		"http://spatialreference.org/ref/sr-org/7634/postgis/"


# ===================================
# City of Chicago Building Footprints
# ===================================
buildings.table : buildings.shp 97634.insert $(PGDATABASE).db
	shp2pgsql -I -D -W "LATIN1" -s 97634 -d $< $(TABLE) | psql 

	# Synthesize address field out of components
	psql -c "ALTER TABLE $(TABLE) ADD COLUMN address varchar(60); \
		 UPDATE $(TABLE) SET address = concat_ws(' ', \
			label_hous, \
			unit_name, \
			pre_dir1, \
			st_name1, \
			suf_dir1, \
			st_type1, \
			'CHICAGO IL' \
		 )"
	
	# Create a `latlng` geometry column.
	psql -c "SELECT AddGeometryColumn('$(TABLE)', 'stateplane', 97634, 'POINT', 2); \
		UPDATE $(TABLE) SET stateplane = \
			ST_SetSRID(ST_MakePoint(x_coord, y_coord), 97634); \
		SELECT AddGeometryColumn('$(TABLE)', 'latlng', 4326, 'POINT', 2); \
		UPDATE $(TABLE) SET latlng = ST_Transform(stateplane, 4326)"

	touch $@

buildings.shp : buildings.zip
	unzip -j $<
	touch $@

buildings.zip : 
	wget --no-use-server-timestamps -O $@ "https://data.cityofchicago.org/api/geospatial/hz9b-7nh8?method=export&format=Shapefile"


# ================================================
# Cook County Address Points (canonical addresses)
# ================================================
addresses.table : addressPointChi.shp $(PGDATABASE).db
	# Synthesize address field out of components.
	shp2pgsql -I -s 4326 -d $< $(TABLE) | psql

	# Synthesize address field out of components.
	psql -c "ALTER TABLE $(TABLE) ADD COLUMN address varchar(171); \
		UPDATE $(TABLE) SET address = concat_ws(' ', \
			addrnocom, \
			stnamecom, \
			uspspn, \
			uspsst, \
			zip5 \
		)"

	# Create a `latlng` geometry column.
	psql -c \
	       "SELECT AddGeometryColumn('$(TABLE)', 'latlng', 4326, 'POINT', 2); \
		UPDATE $(TABLE) SET latlng = CASE \
			WHEN longitude IS NULL OR latitude IS NULL \
			THEN ST_SetSRID(ST_MakePoint(0.0, 0.0), 4326) \
			ELSE ST_GeomFromText( \
				'POINT(' || \
					concat_ws(' ', longitude, latitude) || \
				')', 4326 \
			) END"

	# Index 'pin' to improve performance of join.
	psql -c "CREATE INDEX $(TABLE)_pin_idx ON $(TABLE) (pin)"

	touch $@

addressPointChi.shp : addresses.zip
	unzip -j $<
	touch $@

addresses.zip :
	wget --no-use-server-timestamps -O $@ "https://datacatalog.cookcountyil.gov/api/geospatial/jev2-4wjs?method=export&format=Shapefile"


# ===========================
# Database setup and teardown
# ===========================
$(PGDATABASE).db :
	createdb $(PGDATABASE) -U $(PGUSER)
	sudo -u postgres --preserve-env \
		psql -U postgres -c "CREATE EXTENSION postgis"
	touch $@

.PHONY : $(PGDATABASE).clean
$(PGDATABASE).clean :
	dropdb $(PGDATABASE) -U $(PGUSER) --if-exists	
	rm -f *.db
	rm -f *.table
	rm -f *.insert

