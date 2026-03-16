import asyncio


async def simple_async() -> str:
    """Simple async function."""
    await asyncio.sleep(0.1)
    return "done"


async def async_with_await(url: str) -> str:
    """Async function with await expression."""
    result = await asyncio.sleep(0)
    return str(result)


async def async_for_loop(aiterable) -> list:
    """Async function with async for."""
    results = []
    async for item in aiterable:
        results.append(item)
    return results


async def async_with_statement(path: str) -> str:
    """Async function with async with."""
    async with asyncio.Lock() as lock:
        result = "locked"
    return result


async def async_gather(tasks: list) -> list:
    """Async function using gather."""
    results = await asyncio.gather(*tasks)
    return list(results)


async def async_try_except() -> str:
    """Async function with try/except."""
    try:
        result = await asyncio.sleep(0)
        return "success"
    except asyncio.TimeoutError:
        return "timeout"
    except Exception:
        return "error"
