
qgis_process run "NIST FDS:Export FDS case" --project_path="cern_meyrin.qgs" --distance_units=meters --area_units=m2 --ellipsoid=EPSG:7030 --chid=cern_meyrin_geom --fds_path="output" --extent="6.048008498,6.049552799,46.232493265,46.233460112 [EPSG:4326]" --pixel_size=1 --dem_layer="data_layers/dem_layer.tif" --landuse_type_filepath= --text_filepath= --tex_pixel_size=0.1 --nmesh=4 --cell_size=1 --export_obst=false --UtmGrid=TEMPORARY_OUTPUT --ClippedDemLayer=TEMPORARY_OUTPUT --UtmDemPoints=TEMPORARY_OUTPUT --UtmInterpolatedDemLayer=TEMPORARY_OUTPUT --ExtentDebug=TEMPORARY_OUTPUT --dem_sampling=2
cd output
fds cern_meyrin_geom.fds
smokeview -runscript cern_meyrin_geom
cd ..
