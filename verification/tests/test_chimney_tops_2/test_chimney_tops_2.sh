
qgis_process run "NIST FDS:Export FDS case" \
    --project_path="Chimney_Tops_2.qgs" \
    --distance_units=meters \
    --area_units=m2 \
    --ellipsoid=EPSG:7019 \
    --chid="Chimney_Tops_2" \
    --fds_path="output" \
    --extent="1110975.681700000,1129042.423100000,1465221.682400000,1486081.471700000 [EPSG:5070]" \
    --pixel_size=30 \
    --dem_layer="data_layers/LC20_Elav_220_Abrev.tif" \
    --landuse_layer="data_layers/LC22_F13_220_Abrev.tif" \
    --landuse_type_filepath="data_sheets/Landfire.gov_F13.csv" \
    --fire_layer="data_layers/init_fire_extent.gpkg" \
    --text_filepath= \
    --tex_pixel_size=10 \
    --nmesh=264 \
    --export_obst=false \
    --t_begin=0 \
    --t_end=0 \
    --wind_filepath="data_sheets/Chimney_Tops_2_Wind.csv" \
    --UtmGrid=TEMPORARY_OUTPUT \
    --ClippedDemLayer=TEMPORARY_OUTPUT \
    --UtmDemPoints=TEMPORARY_OUTPUT \
    --UtmInterpolatedDemLayer=TEMPORARY_OUTPUT \
    --ExtentDebug=TEMPORARY_OUTPUT \
    --dem_sampling=1

cd output
fds Chimney_Tops_2.fds
smokeview -runscript Chimney_Tops_2
cd ..
