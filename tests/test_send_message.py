"""
Functional/unit tests for message sending and iMessage vs SMS logic.
Run on pre-commit; commits are blocked if these fail.
"""
import sqlite3
import unittest
from unittest.mock import patch, MagicMock

from mac_messages_mcp.messages import (
    normalize_phone_number,
    _imessage_check_error_message,
    _send_message_to_recipient,
    send_message,
)


class TestNormalizePhoneNumber(unittest.TestCase):
    """Test phone number normalization."""

    def test_digits_only(self):
        self.assertEqual(normalize_phone_number("3032575751"), "3032575751")

    def test_strips_formatting(self):
        self.assertEqual(normalize_phone_number("714-376-7892"), "7143767892")
        self.assertEqual(normalize_phone_number("(720) 579-6609"), "7205796609")
        self.assertEqual(normalize_phone_number("+1 650-450-7174"), "16504507174")

    def test_empty_and_falsy(self):
        self.assertEqual(normalize_phone_number(""), "")
        self.assertEqual(normalize_phone_number(None), "")

    def test_keeps_only_digits(self):
        self.assertEqual(normalize_phone_number("303-257-5751 ext. 99"), "303257575199")


class TestImessageCheckErrorMessage(unittest.TestCase):
    """Test error message when iMessage availability check fails."""

    @patch("mac_messages_mcp.messages.check_messages_db_access")
    def test_operational_error_returns_db_check(self, mock_db_access):
        mock_db_access.return_value = "ERROR: Full Disk Access required"
        exc = sqlite3.OperationalError("database is locked")
        result = _imessage_check_error_message(exc, "3032575751")
        self.assertEqual(result, "ERROR: Full Disk Access required")
        mock_db_access.assert_called_once()

    @patch("mac_messages_mcp.messages.check_messages_db_access")
    def test_database_in_message_returns_db_check(self, mock_db_access):
        mock_db_access.return_value = "Check permissions"
        result = _imessage_check_error_message(Exception("Cannot open database"), "7143767892")
        self.assertEqual(result, "Check permissions")
        mock_db_access.assert_called_once()

    @patch("mac_messages_mcp.messages.check_messages_db_access")
    def test_full_disk_in_message_returns_db_check(self, mock_db_access):
        mock_db_access.return_value = "Grant Full Disk Access"
        result = _imessage_check_error_message(Exception("full disk access denied"), "7205796609")
        self.assertEqual(result, "Grant Full Disk Access")
        mock_db_access.assert_called_once()

    def test_generic_error_returns_user_message_with_recipient(self):
        result = _imessage_check_error_message(ValueError("bad format"), "3032575751")
        self.assertIn("3032575751", result)
        self.assertIn("iMessage", result)
        self.assertIn("bad format", result)
        self.assertIn("check the number", result.lower())


class TestSendMessageToRecipient(unittest.TestCase):
    """Test _send_message_to_recipient branching (iMessage vs SMS, errors)."""

    @patch("mac_messages_mcp.messages._send_message_direct")
    @patch("mac_messages_mcp.messages._check_imessage_availability")
    def test_phone_with_imessage_sends_via_direct(self, mock_check, mock_direct):
        mock_check.return_value = True
        mock_direct.return_value = "Message sent successfully via iMessage to Brian"
        result = _send_message_to_recipient("3032575751", "Hi", contact_name="Brian", group_chat=False)
        mock_check.assert_called_once_with("3032575751")
        mock_direct.assert_called_once()
        self.assertIn("iMessage", result)

    @patch("mac_messages_mcp.messages._send_message_sms")
    @patch("mac_messages_mcp.messages._check_imessage_availability")
    def test_phone_without_imessage_sends_via_sms(self, mock_check, mock_sms):
        mock_check.return_value = False
        mock_sms.return_value = "SMS sent successfully to Brian"
        result = _send_message_to_recipient("3032575751", "Hi", contact_name="Brian", group_chat=False)
        mock_check.assert_called_once_with("3032575751")
        mock_sms.assert_called_once()
        self.assertIn("SMS", result)

    @patch("mac_messages_mcp.messages.check_messages_db_access")
    @patch("mac_messages_mcp.messages._check_imessage_availability")
    def test_phone_when_check_raises_operational_error_returns_db_message(self, mock_check, mock_db_access):
        mock_check.side_effect = sqlite3.OperationalError("locked")
        mock_db_access.return_value = "ERROR: Grant Full Disk Access"
        result = _send_message_to_recipient("3032575751", "Hi", group_chat=False)
        self.assertEqual(result, "ERROR: Grant Full Disk Access")
        mock_db_access.assert_called_once()

    @patch("mac_messages_mcp.messages._check_imessage_availability")
    def test_phone_when_check_raises_generic_returns_error_no_send(self, mock_check):
        mock_check.side_effect = ValueError("malformed")
        result = _send_message_to_recipient("3032575751", "Hi", group_chat=False)
        self.assertIn("Cannot determine", result)
        self.assertIn("3032575751", result)
        self.assertIn("malformed", result)

    @patch("mac_messages_mcp.messages._send_message_direct")
    def test_non_phone_recipient_uses_direct(self, mock_direct):
        mock_direct.return_value = "Message sent to test@example.com"
        result = _send_message_to_recipient("test@example.com", "Hi", group_chat=False)
        mock_direct.assert_called_once()
        self.assertIn("sent", result)


class TestSendMessagePublic(unittest.TestCase):
    """Test public send_message() entrypoint delegates correctly."""

    @patch("mac_messages_mcp.messages._send_message_to_recipient")
    def test_clean_phone_delegates_to_recipient(self, mock_recipient):
        mock_recipient.return_value = "Message sent successfully to 3032575751"
        result = send_message("303-257-5751", "Hi")
        mock_recipient.assert_called_once()
        self.assertEqual(result, "Message sent successfully to 3032575751")

    def test_short_number_rejected_not_sent(self):
        """Truncated numbers (e.g. 714 from 714-376-7892) must not be sent."""
        result = send_message("714", "Hi")
        self.assertIn("too short", result.lower())
        self.assertIn("3 digits", result)
        self.assertIn("714-376-7892", result)


if __name__ == "__main__":
    unittest.main()
