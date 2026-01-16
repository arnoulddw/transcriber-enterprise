
import pytest
from unittest.mock import MagicMock, patch
from app.services.file_service import DEFAULT_CHUNK_LENGTH_MS, split_audio_file

def test_default_chunk_length_constant():
    """Verify that the DEFAULT_CHUNK_LENGTH_MS constant is set to 7 minutes."""
    expected_ms = 7 * 60 * 1000
    assert DEFAULT_CHUNK_LENGTH_MS == expected_ms, f"Expected {expected_ms}ms (7 min), but got {DEFAULT_CHUNK_LENGTH_MS}ms"

@patch('app.services.file_service.AudioSegment')
@patch('app.services.file_service.os.path.exists')
@patch('app.services.file_service.validate_file_path')
@patch('app.services.file_service.os.path.getsize')
def test_split_audio_file_uses_default_chunk_length(mock_getsize, mock_validate, mock_exists, mock_audio_segment):
    """
    Verify that split_audio_file uses the default chunk length when not specified.
    We'll mock a 15-minute audio file and expect 3 chunks (7+7+1).
    """
    # Setup mocks
    mock_exists.return_value = True
    mock_validate.return_value = True
    mock_getsize.return_value = 1000 # Small file size to avoid dynamic resizing logic triggering
    
    # Mock AudioSegment instance
    mock_audio = MagicMock()
    mock_audio.__len__.return_value = 15 * 60 * 1000 # 15 minutes
    mock_audio.frame_rate = 16000
    mock_audio.channels = 1
    mock_audio.sample_width = 2
    
    # Mock slicing to return a dummy chunk
    mock_chunk = MagicMock()
    mock_audio.__getitem__.return_value = mock_chunk
    
    mock_audio_segment.from_file.return_value = mock_audio
    
    # Call function without specifying chunk_length_ms
    chunks = split_audio_file("/fake/path/audio.mp3", "/fake/temp/dir")
    
    # Verification
    # 15 minutes / 7 minutes = 2.14 -> ceil -> 3 chunks
    assert len(chunks) == 3
    
    # Verify export calls
    # We expect 3 exports. 
    # The slicing should happen with step = DEFAULT_CHUNK_LENGTH_MS
    # We can check the slice calls on mock_audio
    
    # Check that __getitem__ was called with slices of 7 minutes
    # Note: slice objects are passed to __getitem__
    # slice(0, 420000, None)
    # slice(420000, 840000, None)
    # slice(840000, 900000, None)
    
    assert mock_audio.__getitem__.call_count == 3
    
    # Check the first slice
    first_call_args = mock_audio.__getitem__.call_args_list[0]
    first_slice = first_call_args[0][0]
    assert first_slice.start == 0
    assert first_slice.stop == 7 * 60 * 1000 # 420000
    
    # Check the second slice
    second_call_args = mock_audio.__getitem__.call_args_list[1]
    second_slice = second_call_args[0][0]
    assert second_slice.start == 7 * 60 * 1000
    assert second_slice.stop == 14 * 60 * 1000
