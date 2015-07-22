include config.mk

.PHONY : all
all : parcels.table taxes.table buildings.table addresses.table


.PHONY: clean
clean :	
	# Use `rm -f` so that no errors are thrown if the files don't exist.

	# Clean up database
	dropdb $(PG_DB) --if-exists -U $(PG_USER)	
	rm -f *.db
	rm -f *.table
	rm -f *.insert

	# Clean up intermediate data files
	rm -f buildings.{dbf,prj,sbn,sbx,shp,shx} # avoid deleting buildings.sql
	rm -f addressPointChi.*
	rm -f ccgisdata-Parcel_2013.*
	rm -f FOI22606.CSV
	rm -f *.zip

	# Clean up downloaded scripts
	rm -f 97634.sql


join :
	# source bin/activate	
	python join.py


# ============================
# Cook County Property Parcels
# ============================
parcels.table : ccgisdata-Parcel_2013.shp $(PG_DB).db
	shp2pgsql -I -s 4326 -d $< $(basename $@) | psql -d $(PG_DB)
	touch $@

ccgisdata-Parcel_2013.shp : parcels.zip
	unzip -j $<
	touch $@

parcels.zip :
	wget --no-use-server-timestamps -O $@ "https://datacatalog.cookcountyil.gov/api/geospatial/5i2c-y2u6?method=export&format=Original"


# =================================================================
# Cook County Tax Assessor's Data (obtained via FOIA request 22606)
# =================================================================
taxes.table : FOI22606.CSV $(PG_DB).db
	psql -d $(PG_DB) -c \
		"CREATE TABLE $(basename $@) \
		 (pin CHAR(14), \
		  mailing_address VARCHAR(50), \
		  property_location VARCHAR(50), \
		  township VARCHAR(13), \
		  property_class INTEGER, \
		  property_classification VARCHAR(150), \
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
	psql -d $(PG_DB) -c \
		"COPY $(basename $@) FROM STDIN WITH CSV QUOTE AS '\"' DELIMITER AS ','"
	touch $@

FOI22606.CSV : foia-22606-2013-10-16.zip
	unzip -j $< "FOI 22606/$@"
	touch $@

foia-22606-2013-10-16.zip :
	wget --no-use-server-timestamps https://s3.amazonaws.com/purple-giraffe-data/$@


# =========================
# Illinois State Plane SRID
# =========================
97634.insert : 97634.sql $(PG_DB).db
	# Chicago Building Footprints dataset has coordinates in the IL State Plane
	# coordinate system (also see Cook County Address Points metadata).
	# Note that PostGIS doesn't accept the ESRI:102671 SRID, so I'm using
	# SR-ORG:7634, which is very similar, instead.
	sudo su postgres -c "psql $(PG_DB) -f $<"
	touch $@

97634.sql :
	wget --no-use-server-timestamps -O $@ \
		"http://spatialreference.org/ref/sr-org/7634/postgis/"


# ===================================
# City of Chicago Building Footprints
# ===================================
buildings.table : buildings.shp buildings.sql 97634.insert $(PG_DB).db
	shp2pgsql -I -D -W "LATIN1" -s 97634 -d $< $(basename $@) | psql -d $(PG_DB)
	psql -d $(PG_DB) -f $(word 2, $^)
	touch $@

buildings.shp : buildings.zip
	unzip -j $<
	touch $@

buildings.zip : 
	wget --no-use-server-timestamps -O $@ "https://data.cityofchicago.org/api/geospatial/qv97-3bvb?method=export&format=Shapefile"


# ================================================
# Cook County Address Points (canonical addresses)
# ================================================
addresses.table : addressPointChi.shp addresses.sql $(PG_DB).db
	# Synthesize address field out of components.
	shp2pgsql -I -s 4326 -d $< $(basename $@) | psql -d $(PG_DB)
	psql -d $(PG_DB) -f $(word 2, $^)
	touch $@

addressPointChi.shp : addresses.zip
	unzip -j $<
	touch $@

addresses.zip :
	wget --no-use-server-timestamps -O $@ "https://datacatalog.cookcountyil.gov/api/geospatial/jev2-4wjs?method=export&format=Shapefile"


# ==============
# Database setup
# ==============
$(PG_DB).db :
	createdb $(PG_DB) -U $(PG_USER)
	sudo su postgres -c "psql -d $(PG_DB) -c \"CREATE EXTENSION postgis\""
	touch $@

