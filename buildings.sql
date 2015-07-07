ALTER TABLE buildings ADD COLUMN stateplane GEOMETRY(POINT, 97634);
SELECT AddGeometryColumn('buildings', 'stateplane', 97634, 'POINT', 2);
UPDATE buildings SET stateplane = ST_SetSRID(ST_MakePoint(x_coord, y_coord), 97634);

ALTER TABLE buildings ADD COLUMN latlng GEOMETRY(POINT, 4326);
UPDATE buildings SET latlng = ST_Transform(stateplane, 4326);

ALTER TABLE buildings ADD COLUMN address varchar(60);
UPDATE buildings SET address = concat_ws(' ', \
    label_hous, unit_name, pre_dir1, st_name1, suf_dir1, st_type1, 'CHICAGO IL');

