"""The Docker desktop transport must stay read-only."""
import json
import unittest
from unittest.mock import Mock, patch

from ui.docker_viewer import DockerRuntimeClient


class DockerRuntimeClientTests(unittest.TestCase):
    def test_status_is_read_from_existing_container(self):
        response = {"ok": True, "protocol": 1, "instance": "abc", "cursor": 3}
        with patch("ui.docker_viewer.subprocess.run",
                   return_value=Mock(returncode=0, stdout=json.dumps(response))) as run:
            actual = DockerRuntimeClient("alrotek-dev-gateway-1").request(
                "status", instance="abc", after=2)
        self.assertEqual(actual, response)
        self.assertEqual(run.call_args.args[0][:5],
                         ["docker", "exec", "-i", "alrotek-dev-gateway-1", "python"])
        self.assertEqual(json.loads(run.call_args.kwargs["input"]),
                         {"instance": "abc", "after": 2})

    def test_mutating_action_never_reaches_docker(self):
        with patch("ui.docker_viewer.subprocess.run") as run:
            with self.assertRaisesRegex(ValueError, "solo lectura"):
                DockerRuntimeClient("alrotek-dev-gateway-1").request("save_gateway")
        run.assert_not_called()

    def test_invalid_container_name_is_rejected(self):
        with self.assertRaises(ValueError):
            DockerRuntimeClient("container; echo unsafe")


if __name__ == "__main__":
    unittest.main()
