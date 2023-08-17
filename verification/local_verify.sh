# Note fds and smv must already be sourced and imagemagick installed
bash headless_verify.sh
rm -rf tests/test_out
rm -rf tests/test_diff
rm -rf tests/test_err
mkdir -p tests/test_out
mkdir -p tests/test_diff
mkdir -p tests/test_err
cp tests/*/output/*.png tests/test_out/
cp ../../qgis2fds.figures/baseline/*/*.png ../../qgis2fds.figures/baseline/
bash compare_images.sh
NUMBER_OF_ERR_FILES=$(ls tests/test_err/ -1 | wc -l)
echo "NUMBER_OF_ERR_FILES=$NUMBER_OF_ERR_FILES"
