# Configure locations
LOG_FILE="$(pwd)/logs/log.txt"
QGISFIGURES_DIR="$(pwd)/../../qgis2fds.figures"
DIFF_DIR="$(pwd)/diff/"

# Check if figure repo exists
if ! test -d $QGISFIGURES_DIR; then
  echo "***Error $QGISFIGURES_DIR directory not found"
  exit 1
fi

# Delete previous log file if it exists
if test -e $LOG_FILE; then
  rm $LOG_FILE
fi

# Make output directories if they do not exist
if ! test -d $DIFF_DIR; then
  mkdir $DIFF_DIR
fi

cd tests/golden_gate/scripts
#bash test_geom.sh
#bash test_geom_min.sh
#bash test_obst.sh
#bash test_obst_min.sh
cd ../../..
cd tests/cern_meyrin/scripts
bash test_geom.sh
bash test_obst.sh
#find . -name "*.png" -o -name "*.fds" -o -name "*.bingeom" | tar -cf ../output.tar.gz -T -

cd ../../../logs
cat log.txt
if grep "err" log.txt; then
  echo "Errors present in log file"
  exit 1
fi

if grep "Err" log.txt; then
  echo "Errors present in log file"
  exit 1
fi
