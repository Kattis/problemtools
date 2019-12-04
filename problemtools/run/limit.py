"""
Module for dealing with resource limits for problemtools runs.
"""

import resource

def check_limit_capabilities(logger):
    """Check if the problemtools process is run with appropriate
    capabilities to set rlimits, and if not, issue warnings.

    Params:
        logger: object to issue warnings to (by calling 'warning' method)

    FIXME: if running as root with a hard stack or cpu rlimit set,
    this will still issue warnings.
    """
    (_, cpu_hard) = resource.getrlimit(resource.RLIMIT_CPU)
    if cpu_hard != resource.RLIM_INFINITY:
        logger.warning("Hard CPU rlimit of %d, runs involving higher CPU limits than this may behave incorrectly."
                       % cpu_hard)

    (_, stack_hard) = resource.getrlimit(resource.RLIMIT_STACK)
    if stack_hard != resource.RLIM_INFINITY:
        logger.warning("Hard stack rlimit of %d so I can't set it to unlimited. I will keep it at %d. If you experience unexpected issues (in particular run-time errors) this may be the cause."
                       % (stack_hard, stack_hard))

    (_, mem_hard) = resource.getrlimit(resource.RLIMIT_AS)
    if mem_hard != resource.RLIM_INFINITY:
        logger.warning("Hard memory rlimit of %.0f MB, runs involving a higher memory limit may behave incorrectly.  If you experience unexpected issues (in particular run-time errors) this may be the cause."
                       % (mem_hard/1024.0/1024.0))



def try_limit(limit, soft, hard):
    """Attempt to set an rlimit, but caps it at the current hard limit for
    the resource (instead of failing like a call to resource.setrlimit
    would).

    Params:
        limit: resource to limit (e.g. resource.RLIMIT_CPU)
        soft: soft limit
        hard: hard limit
    """
    (_, cur_hard) = resource.getrlimit(limit)
    if not __limit_less(soft, cur_hard):
        soft = cur_hard
    if not __limit_less(hard, cur_hard):
        hard = cur_hard
    resource.setrlimit(limit, (soft, hard))



def __limit_less(lim1, lim2):
    """Helper function for comparing two rlimit values, handling "unlimited" correctly.

    Params:
        lim1 (integer): first rlimit
        lim2 (integer): second rlimit

    Returns:
        true if lim1 <= lim2
    """
    if lim2 == resource.RLIM_INFINITY:
        return True
    if lim1 == resource.RLIM_INFINITY:
        return False
    return lim1 <= lim2
