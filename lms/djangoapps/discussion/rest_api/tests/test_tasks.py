"""
Test cases for tasks.py
"""
from unittest import mock
from unittest.mock import Mock

import ddt
import httpretty
from django.conf import settings
from edx_toggles.toggles.testutils import override_waffle_flag
from openedx_events.learning.signals import USER_NOTIFICATION_REQUESTED

from common.djangoapps.student.models import CourseEnrollment
from common.djangoapps.student.tests.factories import UserFactory
from lms.djangoapps.discussion.rest_api.tasks import send_response_notifications
from lms.djangoapps.discussion.rest_api.tests.utils import ThreadMock
from openedx.core.djangoapps.notifications.config.waffle import ENABLE_NOTIFICATIONS
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from xmodule.modulestore.tests.factories import CourseFactory

from ..discussions_notifications import DiscussionNotificationSender
from .test_views import DiscussionAPIViewTestMixin


def _get_mfe_url(course_id, post_id):
    """
    get discussions mfe url to specific post.
    """
    return f"{settings.DISCUSSIONS_MICROFRONTEND_URL}/{str(course_id)}/posts/{post_id}"


@ddt.ddt
@override_waffle_flag(ENABLE_NOTIFICATIONS, active=True)
class TestSendResponseNotifications(DiscussionAPIViewTestMixin, ModuleStoreTestCase):
    """
    Test for the send_response_notifications function
    """

    def setUp(self):
        super().setUp()
        httpretty.reset()
        httpretty.enable()

        self.course = CourseFactory.create()
        self.user_1 = UserFactory.create()
        CourseEnrollment.enroll(self.user_1, self.course.id)
        self.user_2 = UserFactory.create()
        CourseEnrollment.enroll(self.user_2, self.course.id)
        self.user_3 = UserFactory.create()
        CourseEnrollment.enroll(self.user_3, self.course.id)
        self.thread = ThreadMock(thread_id=1, creator=self.user_1, title='test thread')
        self.thread_2 = ThreadMock(thread_id=2, creator=self.user_2, title='test thread 2')
        self.thread_3 = ThreadMock(thread_id=2, creator=self.user_1, title='test thread 3')
        for thread in [self.thread, self.thread_2, self.thread_3]:
            self.register_get_thread_response({
                'id': thread.id,
                'course_id': str(self.course.id),
                'topic_id': 'abc',
                "user_id": thread.user_id,
                "username": thread.username,
                "thread_type": 'discussion',
                "title": thread.title,
            })
        self._register_subscriptions_endpoint()

    def test_basic(self):
        """
        Left empty intentionally. This test case is inherited from DiscussionAPIViewTestMixin
        """

    def test_not_authenticated(self):
        """
        Left empty intentionally. This test case is inherited from DiscussionAPIViewTestMixin
        """

    def test_send_notification_to_thread_creator(self):
        """
        Test that the notification is sent to the thread creator
        """
        handler = mock.Mock()
        USER_NOTIFICATION_REQUESTED.connect(handler)

        # Post the form or do what it takes to send the signal

        send_response_notifications(self.thread.id, str(self.course.id), self.user_2.id, parent_id=None)
        self.assertEqual(handler.call_count, 2)
        args = handler.call_args_list[0][1]['notification_data']
        self.assertEqual([int(user_id) for user_id in args.user_ids], [self.user_1.id])
        self.assertEqual(args.notification_type, 'new_response')
        expected_context = {
            'replier_name': self.user_2.username,
            'post_title': 'test thread',
            'course_name': self.course.display_name,
            'sender_id': self.user_2.id
        }
        self.assertDictEqual(args.context, expected_context)
        self.assertEqual(
            args.content_url,
            _get_mfe_url(self.course.id, self.thread.id)
        )
        self.assertEqual(args.app_name, 'discussion')

    def test_send_notification_to_parent_threads(self):
        """
        Test that the notification signal is sent to the parent response creator and
        parent thread creator, it checks signal is sent with correct arguments for both
        types of notifications.
        """
        handler = mock.Mock()
        USER_NOTIFICATION_REQUESTED.connect(handler)

        self.register_get_comment_response({
            'id': self.thread_2.id,
            'thread_id': self.thread.id,
            'user_id': self.thread_2.user_id
        })

        send_response_notifications(self.thread.id, str(self.course.id), self.user_3.id, parent_id=self.thread_2.id)
        # check if 2 call are made to the handler i.e. one for the response creator and one for the thread creator
        self.assertEqual(handler.call_count, 2)

        # check if the notification is sent to the thread creator
        args_comment = handler.call_args_list[0][1]['notification_data']
        args_comment_on_response = handler.call_args_list[1][1]['notification_data']
        self.assertEqual([int(user_id) for user_id in args_comment.user_ids], [self.user_1.id])
        self.assertEqual(args_comment.notification_type, 'new_comment')
        expected_context = {
            'replier_name': self.user_3.username,
            'post_title': self.thread.title,
            'author_name': 'dummy\'s',
            'course_name': self.course.display_name,
            'sender_id': self.user_3.id
        }
        self.assertDictEqual(args_comment.context, expected_context)
        self.assertEqual(
            args_comment.content_url,
            _get_mfe_url(self.course.id, self.thread.id)
        )
        self.assertEqual(args_comment.app_name, 'discussion')

        # check if the notification is sent to the parent response creator
        self.assertEqual([int(user_id) for user_id in args_comment_on_response.user_ids], [self.user_2.id])
        self.assertEqual(args_comment_on_response.notification_type, 'new_comment_on_response')
        expected_context = {
            'replier_name': self.user_3.username,
            'post_title': self.thread.title,
            'course_name': self.course.display_name,
            'sender_id': self.user_3.id
        }
        self.assertDictEqual(args_comment_on_response.context, expected_context)
        self.assertEqual(
            args_comment_on_response.content_url,
            _get_mfe_url(self.course.id, self.thread.id)
        )
        self.assertEqual(args_comment_on_response.app_name, 'discussion')

    def test_no_signal_on_creators_own_thread(self):
        """
        Makes sure that 1 signal is emitted if user creates response on
        their own thread.
        """
        handler = mock.Mock()
        USER_NOTIFICATION_REQUESTED.connect(handler)
        send_response_notifications(self.thread.id, str(self.course.id), self.user_1.id, parent_id=None)
        self.assertEqual(handler.call_count, 1)

    def test_comment_creators_own_response(self):
        """
        Check incase post author and response auther is same only send
        new comment signal , with your as author_name.
        """
        handler = mock.Mock()
        USER_NOTIFICATION_REQUESTED.connect(handler)

        self.register_get_comment_response({
            'id': self.thread_3.id,
            'thread_id': self.thread.id,
            'user_id': self.thread_3.user_id
        })

        send_response_notifications(self.thread.id, str(self.course.id), self.user_3.id, parent_id=self.thread_2.id)
        # check if 1 call is made to the handler i.e. for the thread creator
        self.assertEqual(handler.call_count, 2)

        # check if the notification is sent to the thread creator
        args_comment = handler.call_args_list[0][1]['notification_data']
        self.assertEqual(args_comment.user_ids, [self.user_1.id])
        self.assertEqual(args_comment.notification_type, 'new_comment')
        expected_context = {
            'replier_name': self.user_3.username,
            'post_title': self.thread.title,
            'author_name': 'your',
            'course_name': self.course.display_name,
            'sender_id': self.user_3.id,
        }
        self.assertDictEqual(args_comment.context, expected_context)
        self.assertEqual(
            args_comment.content_url,
            _get_mfe_url(self.course.id, self.thread.id)
        )
        self.assertEqual(args_comment.app_name, 'discussion')

    @ddt.data(
        (None, 'response_on_followed_post'), (1, 'comment_on_followed_post')
    )
    @ddt.unpack
    def test_send_notification_to_followers(self, parent_id, notification_type):
        """
        Test that the notification is sent to the followers of the thread
        """
        self.register_get_comment_response({
            'id': self.thread.id,
            'thread_id': self.thread.id,
            'user_id': self.thread.user_id
        })
        handler = Mock()
        USER_NOTIFICATION_REQUESTED.connect(handler)

        # Post the form or do what it takes to send the signal
        notification_sender = DiscussionNotificationSender(self.thread, self.course, self.user_2, parent_id=parent_id)
        notification_sender.send_response_on_followed_post_notification()
        self.assertEqual(handler.call_count, 1)
        args = handler.call_args[1]['notification_data']
        # only sent to user_3 because user_2 is the one who created the response
        self.assertEqual([self.user_3.id], args.user_ids)
        self.assertEqual(args.notification_type, notification_type)
        expected_context = {
            'replier_name': self.user_2.username,
            'post_title': 'test thread',
            'course_name': self.course.display_name,
            'sender_id': self.user_2.id,
        }
        if parent_id:
            expected_context['author_name'] = 'dummy'
        self.assertDictEqual(args.context, expected_context)
        self.assertEqual(
            args.content_url,
            _get_mfe_url(self.course.id, self.thread.id)
        )
        self.assertEqual(args.app_name, 'discussion')

    def _register_subscriptions_endpoint(self):
        """
        Registers the endpoint for the subscriptions API
        """
        mock_response = {
            'collection': [
                {
                    '_id': 1,
                    'subscriber_id': str(self.user_2.id),
                    "source_id": self.thread.id,
                    "source_type": "thread",
                },
                {
                    '_id': 2,
                    'subscriber_id': str(self.user_3.id),
                    "source_id": self.thread.id,
                    "source_type": "thread",
                },
            ],
            'page': 1,
            'num_pages': 1,
            'subscriptions_count': 2,
            'corrected_text': None

        }
        self.register_get_subscriptions(self.thread.id, mock_response)


@override_waffle_flag(ENABLE_NOTIFICATIONS, active=True)
class TestSendCommentNotification(DiscussionAPIViewTestMixin, ModuleStoreTestCase):
    """
    Test case to send new_comment notification
    """
    def setUp(self):
        super().setUp()
        httpretty.reset()
        httpretty.enable()

        self.course = CourseFactory.create()
        self.user_1 = UserFactory.create()
        CourseEnrollment.enroll(self.user_1, self.course.id)
        self.user_2 = UserFactory.create()
        CourseEnrollment.enroll(self.user_2, self.course.id)

    def test_basic(self):
        """
        Left empty intentionally. This test case is inherited from DiscussionAPIViewTestMixin
        """

    def test_not_authenticated(self):
        """
        Left empty intentionally. This test case is inherited from DiscussionAPIViewTestMixin
        """

    def test_new_comment_notification(self):
        """
        Tests new comment notification generation
        """
        handler = mock.Mock()
        USER_NOTIFICATION_REQUESTED.connect(handler)

        thread = ThreadMock(thread_id=1, creator=self.user_1, title='test thread')
        response = ThreadMock(thread_id=2, creator=self.user_2, title='test response')
        self.register_get_thread_response({
            'id': thread.id,
            'course_id': str(self.course.id),
            'topic_id': 'abc',
            "user_id": thread.user_id,
            "username": thread.username,
            "thread_type": 'discussion',
            "title": thread.title,
        })
        self.register_get_comment_response({
            'id': response.id,
            'thread_id': thread.id,
            'user_id': response.user_id
        })
        self.register_get_subscriptions(1, {})
        send_response_notifications(thread.id, str(self.course.id), self.user_2.id, parent_id=response.id)
        handler.assert_called_once()
        context = handler.call_args[1]['notification_data'].context
        self.assertEqual(context['author_name'], 'their')
