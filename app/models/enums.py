from enum import Enum


class AuthProvider(str, Enum):
    anonymous = "anonymous"
    google = "google"
    email = "email"
