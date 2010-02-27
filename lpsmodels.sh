#!/bin/bash
lparse $* | smodels -seed $RANDOM
