# tests/functional/test_transcription_management.py
# Contains functional tests for transcription management features.

import io
from unittest.mock import patch, MagicMock

from flask import url_for

from app.models import transcription as transcription_model
from app.services.api_clients.exceptions import TranscriptionApiError

# Constants for tests
SUCCESS_TEST_FILENAME = "test_audio.mp3"
INVALID_TEST_FILENAME = "test_document.txt"


class TestTranscriptionManagement:
    """
    Test suite for transcription management functionalities such as
    file uploads and history pagination.
    """
    @patch("app.api.transcriptions.transcription_service.process_transcription")
    def test_successful_upload_and_transcription(self, mock_process_transcription, logged_in_client):
        """
        Test case for a successful file upload and transcription initiation.
        """
        mock_process_transcription.return_value = None  # The function runs in a thread and does not return a value

        # Prepare the data for the POST request
        data = {
            "api_choice": "whisper",
            "language_code": "en",
            "audio_file": (io.BytesIO(b"test audio data"), SUCCESS_TEST_FILENAME),
        }

        # Make the request to the transcribe endpoint
        response = logged_in_client.post(
            url_for("transcriptions.transcribe_audio"),
            data=data,
            content_type="multipart/form-data",
        )

        # Assert that the request was successful
        assert response.status_code == 202
        response_data = response.get_json()
        assert response_data["message"] == "Transcription job started successfully."
        assert "job_id" in response_data

        # Assert that the background process was called
        mock_process_transcription.assert_called_once()

    def test_upload_with_invalid_file_type(self, logged_in_client):
        """
        Test case for file upload failure due to an invalid file type.
        """
        # Prepare the data for the POST request
        data = {
            "api_choice": "whisper",
            "language_code": "en",
            "audio_file": (io.BytesIO(b"test data"), INVALID_TEST_FILENAME),
        }

        # Make the request to the transcribe endpoint
        response = logged_in_client.post(
            url_for("transcriptions.transcribe_audio"),
            data=data,
            content_type="multipart/form-data",
        )

        # Assert that the request was a bad request
        assert response.status_code == 400
        response_data = response.get_json()
        assert response_data["error"] == "File type not allowed."

    @patch("app.models.transcription_utils.count_visible_user_transcriptions")
    @patch("app.models.transcription_utils.get_paginated_transcriptions")
    def test_history_pagination(self, mock_get_paginated_transcriptions, mock_count_transcriptions, logged_in_client):
        """
        Test case for successful pagination of the transcription history.
        """
        # Mock the functions to simulate a user with more than one page of transcriptions
        mock_count_transcriptions.return_value = 10
        mock_get_paginated_transcriptions.return_value = [
            {"id": i, "filename": f"test_{i}.mp3", "status": "finished", "audio_length_minutes": 1} for i in range(5)
        ]

        # Make a request to the main page
        response = logged_in_client.get(url_for("main.index"))

        # Assert that the request was successful
        assert response.status_code == 200
        assert b"Previous" in response.data
        assert b"Next" in response.data

    @patch("app.models.transcription_utils.count_visible_user_transcriptions")
    @patch("app.models.transcription_utils.get_paginated_transcriptions")
    def test_pagination_items_per_page(self, mock_get_paginated_transcriptions, mock_count_transcriptions, logged_in_client):
        """
        Test case to verify that the number of items per page is correct.
        """
        # Mock the functions to simulate a user with 7 transcriptions
        mock_count_transcriptions.return_value = 7
        mock_get_paginated_transcriptions.return_value = [
            {"id": i, "filename": f"test_{i}.mp3", "status": "finished", "audio_length_minutes": 1} for i in range(5)
        ]

        # Make a request to the first page
        response = logged_in_client.get(url_for("main.index", page=1))

        # Assert that the request was successful and the correct number of items are displayed
        assert response.status_code == 200
        assert response.data.count(b"test_") == 5

        # Mock the return value for the second page
        mock_get_paginated_transcriptions.return_value = [
            {"id": i, "filename": f"test_{i}.mp3", "status": "finished", "audio_length_minutes": 1} for i in range(5, 7)
        ]

        # Make a request to the second page
        response = logged_in_client.get(url_for("main.index", page=2))

        # Assert that the request was successful and the correct number of items are displayed
        assert response.status_code == 200
        assert response.data.count(b"test_") == 2