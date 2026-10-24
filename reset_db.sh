#!/bin/bash
# Reset the working copy (data/campus_customs_new.db) to the original values
# before a full ticket run. The original data/campus_customs.db is never modified.
cd "$(dirname "$0")"
cp data/campus_customs.db data/campus_customs_new.db
echo "Working copy data/campus_customs_new.db reset to original values."
