from rest_framework import serializers


class BarcodeLookupSuccessSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    source = serializers.ChoiceField(choices=["local", "gs1"])
    barcode = serializers.CharField()
    name = serializers.CharField()
    brand = serializers.CharField()
    category = serializers.CharField(required=False, allow_blank=True)
    company = serializers.CharField(required=False, allow_blank=True)
    image = serializers.CharField(required=False, allow_null=True)


class BarcodeLookupFailureSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    error = serializers.CharField(required=False)
