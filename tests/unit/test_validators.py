"""Unit tests for photo validators."""

import io
import pytest
from datetime import datetime
from PIL import Image

from apps.campo.validators import (
    PhotoValidator,
    ValidationResult,
    validate_evidence_photo,
    validate_photo_set,
)


def create_test_image(
    width: int = 1280,
    height: int = 720,
    color: tuple = (128, 128, 128),
    format: str = 'JPEG',
    add_noise: bool = True
) -> bytes:
    """Create a test image with specified dimensions.

    Args:
        width: Image width
        height: Image height
        color: Base RGB color tuple
        format: Image format (JPEG, PNG, etc.)
        add_noise: If True, adds noise for contrast/sharpness (needed to pass validation)
    """
    import numpy as np

    if add_noise and color not in [(10, 10, 10), (250, 250, 250)]:
        # Create image with noise for contrast and sharpness
        np.random.seed(42)  # Reproducible results
        noise = np.random.randint(-50, 51, (height, width, 3), dtype=np.int16)
        base = np.array(color, dtype=np.int16)
        img_array = base + noise
        img_array = np.clip(img_array, 0, 255).astype(np.uint8)
        img = Image.fromarray(img_array, 'RGB')
    else:
        img = Image.new('RGB', (width, height), color)

    buffer = io.BytesIO()
    img.save(buffer, format=format)
    buffer.seek(0)
    return buffer.getvalue()


class TestPhotoValidator:
    """Tests for PhotoValidator class."""

    def test_valid_image_passes(self):
        """A valid image should pass validation."""
        image_bytes = create_test_image(1280, 720)
        validator = PhotoValidator(image_bytes)
        result = validator.validate()

        assert result.is_valid is True
        assert result.score >= 0.6
        assert len(result.errors) == 0

    def test_invalid_format_fails(self):
        """Invalid image format should fail."""
        # Create invalid bytes
        invalid_bytes = b"not an image"
        validator = PhotoValidator(invalid_bytes)
        result = validator.validate()

        assert result.is_valid is False
        assert 'Cannot open image' in result.errors[0]

    def test_low_resolution_fails(self):
        """Image with resolution below minimum should fail."""
        image_bytes = create_test_image(320, 240)  # Too small
        validator = PhotoValidator(image_bytes)
        result = validator.validate()

        assert result.is_valid is False
        assert any('Resolution too low' in e for e in result.errors)

    def test_dark_image_fails(self):
        """Very dark image should fail."""
        image_bytes = create_test_image(1280, 720, color=(10, 10, 10), add_noise=False)
        validator = PhotoValidator(image_bytes)
        result = validator.validate()

        assert result.is_valid is False
        assert any('too dark' in e or 'blurry' in e for e in result.errors)

    def test_overexposed_image_fails(self):
        """Overexposed image should fail."""
        image_bytes = create_test_image(1280, 720, color=(250, 250, 250), add_noise=False)
        validator = PhotoValidator(image_bytes)
        result = validator.validate()

        assert result.is_valid is False
        assert any('overexposed' in e or 'blurry' in e for e in result.errors)

    def test_medium_resolution_warning(self):
        """Medium resolution should trigger warning but pass."""
        image_bytes = create_test_image(800, 600)  # Valid but low
        validator = PhotoValidator(image_bytes)
        result = validator.validate()

        # Should pass but have warning
        assert any('Low resolution' in w for w in result.warnings)

    def test_gps_validation_too_far(self):
        """GPS location too far from expected should fail."""
        image_bytes = create_test_image(1280, 720)
        validator = PhotoValidator(image_bytes)

        # Set up mock metadata
        validator.image = Image.open(io.BytesIO(image_bytes))
        validator.metadata = {
            'latitude': 4.7110,  # Bogotá
            'longitude': -74.0721
        }

        # Expected location in Medellín (far away)
        score = validator._validate_gps(6.2442, -75.5812)

        assert score == 0.0
        assert any('Location too far' in e for e in validator.errors)

    def test_gps_validation_close(self):
        """GPS location close to expected should pass."""
        image_bytes = create_test_image(1280, 720)
        validator = PhotoValidator(image_bytes)

        validator.image = Image.open(io.BytesIO(image_bytes))
        validator.metadata = {
            'latitude': 4.7110,
            'longitude': -74.0721
        }

        # Expected location very close
        score = validator._validate_gps(4.7115, -74.0725)

        assert score == 1.0
        assert len(validator.errors) == 0


class TestValidateEvidencePhoto:
    """Tests for validate_evidence_photo function."""

    def test_returns_dict_with_expected_keys(self):
        """Should return dictionary with all expected keys."""
        image_bytes = create_test_image(1280, 720)
        result = validate_evidence_photo(image_bytes)

        assert 'valid' in result
        assert 'score' in result
        assert 'errors' in result
        assert 'warnings' in result
        assert 'metadata' in result
        assert 'message' in result

    def test_valid_image_returns_valid_true(self):
        """Valid image should return valid=True."""
        image_bytes = create_test_image(1280, 720)
        result = validate_evidence_photo(image_bytes)

        assert result['valid'] is True
        assert result['message'] == 'Photo is valid'

    def test_invalid_image_returns_valid_false(self):
        """Invalid image should return valid=False."""
        result = validate_evidence_photo(b"invalid")

        assert result['valid'] is False
        assert result['message'] != 'Photo is valid'


class TestValidatePhotoSet:
    """Tests for validate_photo_set function."""

    def test_complete_set_passes(self):
        """Complete set of valid photos should pass."""
        photos = [
            {'type': 'ANTES', 'bytes': create_test_image(1280, 720)},
            {'type': 'DURANTE', 'bytes': create_test_image(1280, 720)},
            {'type': 'DESPUES', 'bytes': create_test_image(1280, 720)},
        ]

        result = validate_photo_set(photos)

        assert result['all_valid'] is True
        assert len(result['missing_types']) == 0
        assert result['message'] == 'All photos valid'

    def test_missing_type_fails(self):
        """Missing photo type should fail."""
        photos = [
            {'type': 'ANTES', 'bytes': create_test_image(1280, 720)},
            {'type': 'DURANTE', 'bytes': create_test_image(1280, 720)},
            # Missing DESPUES
        ]

        result = validate_photo_set(photos)

        assert result['all_valid'] is False
        assert 'DESPUES' in result['missing_types']
        assert 'Missing photo types' in result['message']

    def test_invalid_photo_fails(self):
        """Set with invalid photo should fail."""
        photos = [
            {'type': 'ANTES', 'bytes': create_test_image(1280, 720)},
            {'type': 'DURANTE', 'bytes': b"invalid"},  # Invalid
            {'type': 'DESPUES', 'bytes': create_test_image(1280, 720)},
        ]

        result = validate_photo_set(photos)

        assert result['all_valid'] is False
        assert result['results']['DURANTE']['valid'] is False

    def test_empty_set_fails(self):
        """Empty photo set should fail."""
        result = validate_photo_set([])

        assert result['all_valid'] is False
        assert len(result['missing_types']) == 3


class TestHaversineDistance:
    """Tests for distance calculation."""

    def test_same_point_zero_distance(self):
        """Same point should have zero distance."""
        validator = PhotoValidator(b"")
        distance = validator._haversine_distance(4.7110, -74.0721, 4.7110, -74.0721)

        assert distance == 0.0

    def test_known_distance(self):
        """Known distance between cities."""
        validator = PhotoValidator(b"")
        # Bogotá to Medellín ~ 240 km straight-line distance
        distance = validator._haversine_distance(
            4.7110, -74.0721,  # Bogotá
            6.2442, -75.5812   # Medellín
        )

        assert 200 < distance < 280  # Approximate straight-line distance

    def test_short_distance(self):
        """Short distance calculation."""
        validator = PhotoValidator(b"")
        # About 1 km apart
        distance = validator._haversine_distance(
            4.7110, -74.0721,
            4.7200, -74.0721
        )

        assert 0.5 < distance < 1.5
