#!/usr/bin/env bash

#BASE_DIR=$1
#NEW_DIR=$2
#DIFF_DIR=$3
#ERROR_DIR=$4
#TOLERANCE=$5

BASE_DIR=../../qgis2fds.figures/baseline
NEW_DIR=tests/test_out
DIFF_DIR=tests/test_diff
ERROR_DIR=tests/test_err
TOLERANCE=0.025
METRIC=rmse

file_list=$DIFF_DIR/file_list

for f in $NEW_DIR/*.png; do
  base=`basename $f`
  echo "checking $base..."
  blur_base=blur_$base
  from_file=$BASE_DIR/$base
  blur_from_file=$BASE_DIR/$blur_base
  to_file=$NEW_DIR/$base
  blur_to_file=$NEW_DIR/$blur_base
  diff_file=$DIFF_DIR/$base
  diff_file_changed=$DIFF_DIR/$base.changed
  diff_file_metric=$DIFF_DIR/$base.metric
  rm -f $diff_file $diff_file_changed $diff_file_metric
  if [[ -e $from_file ]] && [[ -e $to_file ]]; then
    convert $from_file -blur 0x2 $blur_from_file
    convert $to_file   -blur 0x2 $blur_to_file
    diff=`compare -metric $METRIC $blur_from_file $blur_to_file $diff_file |& awk -F'('  '{printf $2}' | awk -F')' '{printf $1}i'`
    composite $blur_from_file $blur_to_file -compose difference /tmp/diff.$$.png

    SETGRAY=
    if [ "$SETGRAY" == "1" ]; then
      convert /tmp/diff.$$.png   -channel    RGB -negate /tmp/diff2.$$.png
      convert /tmp/diff2.$$.png  -colorspace Gray $diff_file
      rm -f /tmp/diff.$$.png
      rm -f /tmp/diff2.$$.png
    else
      convert /tmp/diff.$$.png -channel RGB -negate $diff_file
      rm -f /tmp/diff.$$.png
    fi
    rm -f $blur_from_file $blur_to_file
    if [ "$diff" == "" ]; then
      diff=0
    fi
    if [[ $diff == *"e"* ]]; then
      diff=$(printf "%.6f" $diff)
    fi
    echo $diff > $diff_file_metric
    echo $base $diff >> $file_list
    if [[ "$diff" != "0" ]] && [[ ! $diff == *"e"* ]]; then
      iftest=`echo "${diff} > ${TOLERANCE}" | bc`
      if [ 1 -eq $iftest ]; then
        echo "***$FYI: The image $base has changed. $METRIC error=$diff > $TOLERANCE"
        touch $diff_file_changed
        IMAGE_ERRORS=$((IMAGE_ERRORS + 1))
#        cp $base $ERROR_SUBDIR/.
        cp $f $ERROR_DIR/.
      else
        echo "PASSED: The image $base has not changed. $METRIC error=$diff <= $TOLERANCE"
      fi
    fi
    if [[ "$diff" != "0" ]]; then
      DIFFS=$((DIFFS + 1))
    fi
  fi
  if [[ ! -e $from_file ]]; then
    echo "***$FYI: The base image $from_file does not exist."
    echo "            Copy $to_file to the fig repo"
    cp $f $ERROR_DIR/.
  fi
done
