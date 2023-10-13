"""
Serializers for the Agreements app
"""
from rest_framework import serializers

from openedx.core.djangoapps.agreements.models import IntegritySignature, LTIPIISignature
from openedx.core.lib.api.serializers import CourseKeyField


class IntegritySignatureSerializer(serializers.ModelSerializer):
    """
    Serializer for the IntegritySignature model
    """
    username = serializers.CharField(source='user.username')
    course_id = CourseKeyField(source='course_key')
    created_at = serializers.DateTimeField(source='created')

    class Meta:
        model = IntegritySignature()


class LTIPIISignatureSerializer(serializers.ModelSerializer):
    """
    Serializer for LTIPIISignature model
    """
    username = serializers.CharField(source='user.username')
    course_id = CourseKeyField(source='course_key')
    lti_tools = serializers.JSONField(False, None)
    created_at = serializers.DateTimeField(source='created')

    class Meta:
        model = LTIPIISignature()
        fields = ('username', 'course_id', 'lti_tools', 'created_at')
