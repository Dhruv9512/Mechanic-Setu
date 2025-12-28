# core/serializers.py

from rest_framework import serializers
from .models import MapAd

class MapAdSerializer(serializers.ModelSerializer):
    # Map backend snake_case to frontend camelCase
    businessName = serializers.CharField(source='business_name')
    logo = serializers.URLField(source='logo_url')
    link = serializers.URLField(source='link_url')
    offerTitle = serializers.CharField(source='offer_title')
    offerSubtitle = serializers.CharField(source='offer_subtitle')
    offerPrice = serializers.CharField(source='offer_price')
    bgGradient = serializers.JSONField(source='bg_gradient')

    class Meta:
        model = MapAd
        fields = [
            'id', 
            'businessName', 
            'logo', 
            'link', 
            'latitude', 
            'longitude', 
            'description', 
            'offerTitle', 
            'offerSubtitle', 
            'offerPrice', 
            'bgGradient'
        ]