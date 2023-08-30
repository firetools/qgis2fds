#!/usr/bin/env bash

# Get case name
ABSOLUTE_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
IFS='/'
read -a strarr <<< $ABSOLUTE_PATH
CASEDIRNAME=${strarr[-3]}
IFS=""

# Get CHID
cd ../QGIS
CHID=$(basename "$0" ".sh")

# Configure parameters
BASE_DIR="$(pwd)/../../../../../qgis2fds.figures/tests/$CASEDIRNAME/FDS/"
NEW_DIR="$(pwd)/../FDS/"
DIFF_DIR="$(pwd)/../../../diff/"
LOG_FILE="$(pwd)/../../../logs/log.txt"
TOLERANCE=0.025

# Make output directories if they do not exist
if ! test -d $DIFF_DIR; then
  mkdir $DIFF_DIR
fi

# Clean
rm -f $NEW_DIR/$CHID*  # does not rm .gitignore

# Run QGIS

cd ../QGIS
CHID=$(basename "$0" ".sh")
qgis_process run 'NIST FDS:Export FDS case' \
    --project_path="golden_gate.qgs" \
    --distance_units=meters \
    --area_units=m2 \
    --ellipsoid=EPSG:7019 \
    --chid="$CHID" \
    --fds_path='../FDS' \
    --extent_layer='layers/Extent.gpkg' \
    --pixel_size=10 \
    --origin='-2279360.204651,1963332.020198 [EPSG:5070]' \
    --dem_layer='layers/US_DEM2016_local.tif' \
    --landuse_layer='layers/US_200F13_20_local.tif' \
    --landuse_type_filepath='sheets/Landfire F13 landuse type.csv' \
    --fire_layer='layers/Fire.gpkg' \
    --tex_pixel_size=1 \
    --nmesh=4 \
    --cell_size=5 \
    --t_begin=0 \
    --t_end=0 \
    --wind_filepath='sheets/wind.csv' \
    --text_filepath='' \
    --export_obst=true 

# Run FDS

cd ../FDS

cat << EOF > "$CHID.ini"
VIEWPOINT5
 0 -4 3
 0.500000 -1.533945 0.092708 1.000000 2
 0.000000 0.000000 90.000000 0
 0.500000 0.452000 0.092708
 -33.000000 32.000000
 1.000000 0.000000 0.000000 0.000000
 0.000000 1.000000 0.000000 0.000000
 0.000000 0.000000 1.000000 0.000000
 0.000000 0.000000 0.000000 1.000000
 0 0 0 0 0 0 0
 -62.159824 -56.685352 429.114441 63.090176 56.540646 463.304108
 iso
EOF

cat << EOF > "$CHID.ssf"
SETVIEWPOINT
 ZMAX
RENDERDOUBLEONCE
 
SETVIEWPOINT
 ZMIN
RENDERDOUBLEONCE
 
SETVIEWPOINT
 YMAX
RENDERDOUBLEONCE
 
SETVIEWPOINT
 YMIN
RENDERDOUBLEONCE
 
SETVIEWPOINT
 XMAX
RENDERDOUBLEONCE
 
SETVIEWPOINT
 XMIN
RENDERDOUBLEONCE
 
SETVIEWPOINT
 iso
RENDERDOUBLEONCE
EOF

fds "$CHID.fds"
smokeview -runscript "$CHID"

# Compare images with baseline FIXME
bash ../../../scripts/compare_images.sh $BASE_DIR $NEW_DIR $DIFF_DIR $CHID 0.025 2>&1 | tee -a $LOG_FILE

