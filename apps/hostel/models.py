from django.db import models


class Room(models.Model):
    number = models.CharField(max_length=20)
    capacity = models.PositiveIntegerField(default=2)

    def __str__(self) -> str:
        return self.number


class Resident(models.Model):
    full_name = models.CharField(max_length=255)
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, related_name="residents")

    def __str__(self) -> str:
        return self.full_name
