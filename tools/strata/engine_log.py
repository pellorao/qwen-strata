"""Engine request-log capture around a model stop (kept from the removed Reviewer benchmark runner)."""
from tools.metrics.strata_tokens import parse_engine_log, sum_engine_tokens, engine_rates
from tools.strata.wsl_client import save


def capture_engine_log(installation,model,offset,folder,measurement_host):
    content=measurement_host.log_bytes_since(model,offset).decode(errors='replace')
    (folder/'engine-request-log.txt').write_text(content)
    requests=parse_engine_log(content)
    save(folder/'engine-rates.json',engine_rates(requests))
    return requests,sum_engine_tokens(requests)


def stop_and_capture_engine_log(controller,installation,model,offset,folder,measurement_host=None):
    """Wait for confirmed stop before the final snapshot, including late counters."""
    stopped=controller.stop()
    if stopped.get('status')!='stopped':
        raise RuntimeError('Model stop is unconfirmed; do not capture final counters or start the next instance')
    requests,tokens=capture_engine_log(installation,model,offset,folder,measurement_host)
    return stopped,requests,tokens


def log_offset(installation,model,measurement_host):
    return measurement_host.log_offset(model)
