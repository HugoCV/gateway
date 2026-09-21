import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from application.services.gateway_command_service import GatewayCommandService


class GatewayCommandTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "commands.json"
        self.restart = Mock()
        self.publish = Mock(return_value=True)
        self.service = self.create_service()
        now = datetime.now(timezone.utc)
        self.command = {"version": 1, "commandId": "restart-1", "action": "restart", "params": {},
                        "target": {"organizationId": "org", "gatewayId": "gw"},
                        "issuedAt": now.isoformat(), "expiresAt": (now + timedelta(seconds=60)).isoformat()}

    def create_service(self):
        return GatewayCommandService(self.path, "org", "gw", self.restart, self.publish, Mock())

    def test_success_requires_new_process_not_mqtt_reconnect(self):
        self.service.receive(self.command)
        self.restart.assert_called_once()
        self.service.flush_results()
        self.publish.assert_not_called()
        self.assertEqual(json.loads(self.path.read_text())["commands"]["restart-1"]["status"], "pending")
        next_process = self.create_service()
        next_process.flush_results()
        self.publish.assert_called_once_with({"commandId": "restart-1", "status": "success", "reason": None})

    def test_duplicate_never_restarts_again_and_resends_result(self):
        self.service.receive(self.command)
        self.service.receive(self.command)
        next_process = self.create_service()
        next_process.flush_results()
        next_process.receive(self.command)
        next_process.flush_results()
        self.restart.assert_called_once()
        self.assertEqual(self.publish.call_count, 2)

    def test_result_survives_broker_failure_and_process_restart(self):
        self.service.receive(self.command)
        self.publish.return_value = False
        self.create_service().flush_results()
        self.publish.return_value = True
        self.create_service().flush_results()
        self.create_service().flush_results()
        self.assertEqual(self.publish.call_count, 2)

    def test_expired_unsupported_version_and_action_never_restart(self):
        for changes, reason in [
            ({"expiresAt": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()}, "command_expired"),
            ({"version": 2}, "unsupported_command_version"),
            ({"action": "restart-gateway"}, "unsupported_gateway_command"),
        ]:
            with self.subTest(reason=reason):
                self.service.receive(dict(self.command, commandId=reason, **changes))
                self.service.flush_results()
                self.publish.assert_called_with({"commandId": reason, "status": "failed", "reason": reason})
        self.restart.assert_not_called()

    def test_invalid_target_or_timestamps_never_restart(self):
        for changes in [{"target": {"organizationId": "other", "gatewayId": "gw"}},
                        {"issuedAt": None}, {"expiresAt": "invalid"}, {"commandId": []}]:
            self.service.receive(dict(self.command, **changes))
        self.restart.assert_not_called()

    def test_reused_id_with_different_payload_does_not_execute(self):
        self.service.receive(self.command)
        self.service.receive(dict(self.command, params={"value": "changed"}))
        self.restart.assert_called_once()

    def test_restart_exception_reports_failure(self):
        self.restart.side_effect = RuntimeError("cannot restart")
        self.service.receive(self.command)
        self.service.flush_results()
        self.publish.assert_called_once_with({"commandId": "restart-1", "status": "failed", "reason": "gateway_restart_failed"})

    def test_unwritable_journal_fails_closed(self):
        with patch.object(self.service, "_save", side_effect=OSError("read-only")):
            self.service.receive(self.command)
        self.restart.assert_not_called()

    def test_corrupt_journal_fails_closed(self):
        self.path.write_text("not json")
        self.create_service().receive(self.command)
        self.restart.assert_not_called()

    def test_second_pending_restart_is_rejected(self):
        self.service.receive(self.command)
        self.service.receive(dict(self.command, commandId="restart-2"))
        self.service.flush_results()
        self.restart.assert_called_once()
        self.publish.assert_called_once_with({"commandId": "restart-2", "status": "failed", "reason": "gateway_command_in_progress"})


if __name__ == "__main__":
    unittest.main()
