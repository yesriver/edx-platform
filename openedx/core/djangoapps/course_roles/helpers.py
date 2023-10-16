"""
Helpers for the course roles app.
"""
from django.contrib.auth.models import AnonymousUser
from edx_toggles.toggles import WaffleFlag
from openedx.core.djangoapps.course_roles.models import CourseRolesUserRole
from openedx.core.lib.cache_utils import request_cached
from xmodule.modulestore.django import modulestore


# .. toggle_name: FLAG_USE_PERMISSION_CHECKS
# .. toggle_implementation: WaffleFlag
# .. toggle_default: False
# .. toggle_description: Enabling the toggle will allow the db checks for a users permissions. These are used alongside current
#   roles checks. If the flag is not enabled, only the roles checks will be used.
# .. toggle_use_cases: temporary
# .. toggle_creation_date: 2023-10-17
# .. toggle_target_removal_date: 2023-12-01
# .. toggle_warning:
USE_PERMISSION_CHECKS_FLAG = WaffleFlag('course_roles.use_permission_checks', module_name=__name__) or False  # lint-amnesty, pylint: disable=toggle-missing-annotation


def use_permission_checks():
    """
    Returns ture if permissions checks should be used
    """
    return USE_PERMISSION_CHECKS_FLAG.is_enabled()


@request_cached()
def course_permission_check(user, permission_name, course_id):
    """
    Check if a user has a permission in a course.
    """
    if not use_permission_checks():
        return False
    elif isinstance(user, AnonymousUser):
        return False
    return CourseRolesUserRole.objects.filter(
        user=user,
        role__permissions__name=permission_name,
        course=course_id,
    ).exists()


@request_cached()
def course_permissions_list_check(user, permission_names, course_id):
    """
    Check if a user has all of the given permissions in a course.
    """
    if not use_permission_checks():
        return False
    return all(course_permission_check(user, permission_name, course_id) for permission_name in permission_names)


@request_cached()
def course_permissions_list_check_any(user, permission_names, course_id):
    """
    Check if a user has ANY of the given permissions in a course.
    """
    return any(course_permission_check(user, permission_name, course_id) for permission_name in permission_names)


@request_cached()
def organization_permission_check(user, permission_name, organization_name):
    """
    Check if a user has a permission in an organization.
    """
    if not use_permission_checks():
        return False
    elif isinstance(user, AnonymousUser):
        return False
    return CourseRolesUserRole.objects.filter(
        user=user,
        role__permissions__name=permission_name,
        course__isnull=True,
        org__name=organization_name,
    ).exists()


@request_cached()
def organization_permissions_list_check(user, permission_names, organization_name):
    """
    Check if a user has all of the given permissions in an organization.
    """
    if not use_permission_checks():
        return False
    return all(
        organization_permission_check(user, permission_name, organization_name) for permission_name in permission_names
    )


@request_cached()
def course_or_organization_permission_check(user, permission_name, course_id, organization_name=None):
    """
    Check if a user has a permission in an organization or a course.
    """
    if not use_permission_checks():
        return False
    elif isinstance(user, AnonymousUser):
        return False
    if organization_name is None:
        course = modulestore().get_course(course_id)
        if course:
            organization_name = course.org
        else:
            return course_permission_check(user, permission_name, course_id)
    return (course_permission_check(user, permission_name, course_id) or
            organization_permission_check(user, permission_name, organization_name)
            )


@request_cached()
def course_or_organization_permission_list_check(user, permission_names, course_id, organization_name=None):
    """
    Check if a user has all of the given permissions in an organization or a course.
    """
    if not use_permission_checks():
        return False
    return all(
        course_or_organization_permission_check(user, permission_name, course_id, organization_name)
        for permission_name in permission_names
    )
