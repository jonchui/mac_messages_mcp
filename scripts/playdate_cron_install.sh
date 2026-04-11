#!/bin/bash
# Install cron job to poll playdate replies every 10 min and notify you.
# Run once: ./scripts/playdate_cron_install.sh
#
# You must set PLAYDATE_NOTIFY_TO to your phone number (e.g. 13035551234) so you get
# an iMessage when someone replies, with suggested replies to approve (Y1 N2 Y3).

set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
CRON_CMD="*/10 * * * * PLAYDATE_NOTIFY_TO=\${PLAYDATE_NOTIFY_TO} cd $REPO && uv run python scripts/poll_playdate_replies.py --hours 48 >> /tmp/playdate_poll.log 2>&1"

if [ -z "$PLAYDATE_NOTIFY_TO" ]; then
  echo "Set your phone number first:"
  echo "  export PLAYDATE_NOTIFY_TO=13035551234"
  echo "Then run this script again so the cron job has your number."
  echo ""
  echo "To add the cron job manually (replace with your number):"
  echo "  crontab -e"
  echo "  Add: */10 * * * * PLAYDATE_NOTIFY_TO=13035551234 cd $REPO && uv run python scripts/poll_playdate_replies.py --hours 48 >> /tmp/playdate_poll.log 2>&1"
  exit 0
fi

# Install cron with the number in the environment
( crontab -l 2>/dev/null | grep -v "poll_playdate_replies" ; echo "*/10 * * * * PLAYDATE_NOTIFY_TO=$PLAYDATE_NOTIFY_TO cd $REPO && uv run python scripts/poll_playdate_replies.py --hours 48 >> /tmp/playdate_poll.log 2>&1" ) | crontab -
echo "Cron installed: poll playdate replies every 10 min, notify to $PLAYDATE_NOTIFY_TO"
echo "Log: /tmp/playdate_poll.log"
