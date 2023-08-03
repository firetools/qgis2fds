
qgis_process run "NIST FDS:Export FDS case" --project_path="golden_gate_local.qgs" --distance_units=meters --area_units=m2 --ellipsoid=EPSG:7030 --chid=golden_gate_local_geom --fds_path="output" --extent="-122.491206899,-122.481181391,37.827810126,37.833676214 [EPSG:4326]" --pixel_size=30 --dem_layer="data_layers/US_DEM2016_local.tif" --landuse_layer="data_layers/US_200F13_20_local.tif" --landuse_type_filepath="Landfire.gov_F13.csv" --fire_layer="data_layers/fire.shx|layername=fire" --text_filepath="wind.csv" -tex_layer="data_layers/OpenStreetMap.tif" --tex_pixel_size=1 --origin="-2279076.207440,1963675.963121 [EPSG:5070]" --nmesh=4 --cell_size=10 --export_obst=false --UtmGrid=TEMPORARY_OUTPUT --ClippedDemLayer=TEMPORARY_OUTPUT --UtmDemPoints=TEMPORARY_OUTPUT --UtmInterpolatedDemLayer=TEMPORARY_OUTPUT --ExtentDebug=TEMPORARY_OUTPUT --dem_sampling=1
cd output
fds golden_gate_local_geom.fds
smokeview -runscript golden_gate_local_geom
cd ..
