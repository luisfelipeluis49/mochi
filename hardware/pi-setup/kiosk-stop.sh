#!/usr/bin/env bash
# Close the kiosk browser.
pkill -f -- "--user-data-dir=$HOME/.cache/mochi-kiosk" && echo "Kiosk closed" || echo "Kiosk was not running"
