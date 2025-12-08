from dotenv import load_dotenv
import os
import httpx
import asyncio

async def call_api(url: str, params=None, headers: dict[str, any]=None, method="GET"):
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            api_key = os.getenv("tibco_read_auth_token")
            req_headers = dict(headers)
            req_headers["Authorization"] = api_key
            if method == "GET":
                response = await client.get(url, params=params, headers=req_headers)
            elif method == "POST":
                response = await client.post(url, json=params, headers=req_headers)
            elif method == "PUT":
                api_key = os.getenv("tibco_write_auth_token") # update auth token to write
                req_headers = dict(headers)
                req_headers["Authorization"] = api_key
                response = await client.put(url, json=params, headers=req_headers)
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as e:
            print(f"API call failed: {e}")
            return None


async def run_multiple_calls(call_specs : list[dict[str, any]]):
    """
    call_specs: list of dicts like:
    [
        {"url": "...", "headers": {...}, "params": {...}, "method": "GET"},
        {"url": "...", "headers": {...}, "params": {...}, "method": "POST"}
    ]
    """
    for spec in call_specs:
        print(spec.get("headers"))
    coros = [call_api(spec["url"], params=spec.get("params"), headers=spec.get("headers"), method=spec.get("method", "GET")) for spec in call_specs]
    return await asyncio.gather(*coros)


async def run_call(call_spec: dict[str, any]):
    return await call_api(call_spec["url"], params=call_spec.get("params"), headers=call_spec.get("headers"), method=call_spec.get("method", "GET"))


def run_calls_sync(call_specs):
    return asyncio.run(run_multiple_calls(call_specs))


def run_call_sync(call_spec: dict[str, any]):
    return asyncio.run(run_call(call_spec))

load_dotenv()

