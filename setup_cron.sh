#!/bin/bash
# Install 2x daily cron jobs for automated story generation
# Morning: 08:00  |  Afternoon: 15:00

PYTHON="/home/dung/anaconda3/envs/demo/bin/python"
SCRIPT="/home/dung/Desktop/kids-tiktok-agent/auto_generate.py"
LOG_DIR="/home/dung/Desktop/kids-tiktok-agent/logs"

mkdir -p "$LOG_DIR"

# Remove any existing auto_generate cron entries, then add fresh ones
(
  crontab -l 2>/dev/null | grep -v "auto_generate.py"
  echo "0 8  * * * $PYTHON $SCRIPT >> $LOG_DIR/morning.log 2>&1"
  echo "0 15 * * * $PYTHON $SCRIPT >> $LOG_DIR/afternoon.log 2>&1"
) | crontab -

echo "Cron jobs installed:"
crontab -l | grep auto_generate
