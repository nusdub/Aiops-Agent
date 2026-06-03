from app.services.kubernetes_provider import DemoKubernetesProvider


def test_demo_provider_returns_stable_unhealthy_pods():
    provider = DemoKubernetesProvider()

    pods = provider.list_pods(namespace="prod", workload="checkout-api")
    events = provider.list_events(namespace="prod", workload="checkout-api")

    assert provider.status().ready is True
    assert len(pods) == 2
    assert all(pod.reason in {"CrashLoopBackOff"} for pod in pods)
    assert any(event.reason == "BackOff" for event in events)


def test_demo_provider_service_has_no_ready_endpoint():
    provider = DemoKubernetesProvider()

    result = provider.service_endpoints(namespace="prod", service_name="checkout-api")

    assert result["service_exists"] is True
    assert result["endpoint_count"] == 0
    assert result["not_ready_addresses"]
