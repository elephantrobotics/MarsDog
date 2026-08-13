import json
import unittest

from marsdog_sim2d.feeding_interface import FeedingCoordinator


class FeedingInterfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.coordinator = FeedingCoordinator()

    def _update(
        self,
        *,
        food: bool,
        at_bowl: bool,
        waiting: bool,
        authorized: bool = False,
    ) -> dict:
        return self.coordinator.update_from_ui(
            food_available=food,
            dog_at_bowl=at_bowl,
            waiting_for_food=waiting,
            eating_authorized=authorized,
            active_goal_id="food-goal",
        )

    def test_request_is_rejected_before_dog_reaches_bowl(self) -> None:
        self._update(food=True, at_bowl=False, waiting=False)

        decision = self.coordinator.try_start_eating()

        self.assertFalse(decision.accepted)
        self.assertEqual("DOG_NOT_AT_BOWL", decision.reason)

    def test_request_is_rejected_at_empty_bowl(self) -> None:
        self._update(food=False, at_bowl=True, waiting=True)

        decision = self.coordinator.try_start_eating()

        self.assertFalse(decision.accepted)
        self.assertEqual("NO_FOOD", decision.reason)
        self.assertEqual("WAITING_FOR_FOOD", decision.state["phase"])

    def test_request_authorizes_eating_only_when_food_and_dog_are_ready(self) -> None:
        self._update(food=True, at_bowl=True, waiting=True)

        decision = self.coordinator.try_start_eating()

        self.assertTrue(decision.accepted)
        self.assertEqual("EATING_AUTHORIZED", decision.reason)
        self.assertTrue(decision.state["eatingAuthorized"])
        self.assertEqual("EATING_AUTHORIZED", decision.state["phase"])

    def test_service_authorization_survives_until_ui_processes_event(self) -> None:
        self._update(food=True, at_bowl=True, waiting=True)
        self.assertTrue(self.coordinator.try_start_eating().accepted)

        snapshot = self._update(
            food=True,
            at_bowl=True,
            waiting=True,
            authorized=False,
        )

        self.assertTrue(snapshot["eatingAuthorized"])

    def test_state_json_contains_documented_handshake_fields(self) -> None:
        self._update(food=True, at_bowl=True, waiting=True)

        payload = json.loads(self.coordinator.state_json())

        self.assertEqual("FEEDING_STATE", payload["event_type"])
        self.assertTrue(payload["foodAvailable"])
        self.assertTrue(payload["dogAtBowl"])
        self.assertTrue(payload["waitingForFood"])
        self.assertTrue(payload["waitingForAuthorization"])
        self.assertEqual("food-goal", payload["activeGoalId"])


if __name__ == "__main__":
    unittest.main()
