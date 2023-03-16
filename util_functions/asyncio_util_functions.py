import asyncio
from contextlib import suppress


async def wait_for_psce(fut, timeout):
    """
    Meaning: psce - prevent silent cancel error \n
    This is a changed method 'wait_for()' from library 'asyncio' that prevents 'CancelledError' from being ignored
    while the internal task is finished. \n
    Description of the problem: the base method 'wait_for()' also works in such a way that when the inner task
    is finished or there is no place for it to stop, function 'wait_for()' will return the result even if the inner
    task is canceled, so the 'CancelledError' will not be propagated higher. This method prevents this situation.

    :param fut: future oc coroutine
    :param timeout: timeout, czn be float or int number
    """
    task = asyncio.ensure_future(fut)
    try:
        return await asyncio.shield(asyncio.wait_for(task, timeout=timeout))
    except asyncio.CancelledError:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        raise

