from rest_framework import serializers
from Backend.models import UserSecurityProfile

class UserSecuritySessionSerializers(serializers.ModelSerializer):

    user = serializers.SerializerMethodField()
    class Meta:
        model = UserSecurityProfile
        fields = '__all__'

    def get_user(self, instance):
            return instance.user.clerk_user_name