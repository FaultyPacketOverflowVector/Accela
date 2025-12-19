import os
import logging
from pathlib import Path
from PIL import Image
import numpy as np
import time
import concurrent.futures
from functools import partial
import shutil
import hashlib
import json

from utils.helpers import get_base_path, resource_path

logger = logging.getLogger(__name__)

def process_gif_batch(output_dir, accent_color):
    """
    Process all GIFs from multiple input directories in parallel
    """
    os.makedirs(output_dir, exist_ok=True)

    # Clean up old hex files and non-standard colorized files
    _cleanup_old_files(output_dir)

    # Find all unique GIFs across input directories (first found wins)
    input_dirs = [
        str(get_base_path() / "gifs" / "custom"),
        resource_path("res/gif")
    ]

    gif_list = _find_unique_gifs(input_dirs)

    if not gif_list:
        logger.warning("No GIF files found in any input directory")
        return

    logger.info(f"Found {len(gif_list)} unique GIFs across {len(input_dirs)} directories")

    # Create color-specific subdirectory
    color_subdir = os.path.join(output_dir, accent_color.lstrip('#'))
    os.makedirs(color_subdir, exist_ok=True)

    regeneration_needed = _check_regeneration(gif_list, input_dirs, color_subdir, accent_color)

    if not regeneration_needed:
        logger.info("All GIFs are up to date, updating symlinks only.")
        _update_color_symlinks(gif_list, accent_color, color_subdir, output_dir)
        return

    logger.info(f"Colorizing {len(gif_list)} GIFs with color: {accent_color}")
    start_time = time.time()

    completed_count = _process_gifs(gif_list, input_dirs, color_subdir, accent_color)

    total_time = time.time() - start_time
    logger.info(f"Completed processing {completed_count}/{len(gif_list)} GIFs in {total_time:.2f}s "
                f"({total_time/max(completed_count,1):.2f}s per GIF)")

    _write_hashes_file(color_subdir)

    _update_color_symlinks(gif_list, accent_color, color_subdir, output_dir)

def _cleanup_old_files(output_dir):
    """Remove hex.txt and non-standard colorized files"""
    hex_file_path = os.path.join(output_dir, "hex.txt")
    if os.path.exists(hex_file_path):
        try:
            os.remove(hex_file_path)
            logger.info(f"Removed old hex.txt file: {hex_file_path}")
        except Exception as e:
            logger.warning(f"Could not remove hex.txt file: {e}")

    try:
        for filename in os.listdir(output_dir):
            if "_" in filename:
                file_path = os.path.join(output_dir, filename)
                os.remove(file_path)
                logger.debug(f"Removed non-standard colorized file: {filename}")
    except Exception as e:
        logger.warning(f"Error cleaning up non-standard files: {e}")

def _find_unique_gifs(input_dirs):
    """
    Find all unique GIF files across input directories.
    Returns the first occurrence of each GIF filename found in the directories.
    """
    gif_files = {}

    for input_dir in input_dirs:
        if not os.path.exists(input_dir):
            logger.warning(f"Input directory does not exist: {input_dir}")
            continue

        logger.debug(f"Scanning directory: {input_dir}")
        for filename in os.listdir(input_dir):
            if filename.lower().endswith('.gif'):
                if filename not in gif_files:
                    gif_files[filename] = input_dir
                    logger.debug(f"Found GIF: {filename} in {input_dir}")

    return list(gif_files.keys())

def _check_regeneration(gif_list, input_dirs, color_subdir, accent_color):
    """
    Check if any GIFs need regeneration by comparing hashes
    Returns True if any GIF needs regeneration
    """
    logger.info("Batch checking for regeneration needs...")

    # Load existing hashes
    existing_hashes = _load_hashes(color_subdir)
    needs_regeneration = False

    for gif_name in gif_list:
        source_dir = _find_gif_source(input_dirs, gif_name)
        if not source_dir:
            continue

        input_path = os.path.join(source_dir, gif_name)
        output_path = os.path.join(color_subdir, gif_name)

        # Check if regeneration is needed
        if _should_regenerate_gif(input_path, output_path, gif_name, existing_hashes):
            needs_regeneration = True
            # We can break early if we find at least one that needs regeneration
            break

    return needs_regeneration

def _process_gifs(gif_list, input_dirs, color_subdir, accent_color):
    """
    Process GIFs in parallel batches
    """
    cpu_count = os.cpu_count() or 4
    max_workers = min(cpu_count, len(gif_list), 14) # Cap at 14, I like even numbers :)

    logger.info(f"Processing with {max_workers} workers")

    # Prepare batch data
    batch_data = []
    for gif_name in gif_list:
        source_dir = _find_gif_source(input_dirs, gif_name)
        if source_dir:
            batch_data.append({
                'name': gif_name,
                'source_path': os.path.join(source_dir, gif_name),
                'output_path': os.path.join(color_subdir, gif_name),
                'accent_color': accent_color
            })

    # Process in parallel
    completed_count = 0
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_gif = {
            executor.submit(_process_single_gif_worker, gif_data): gif_data
            for gif_data in batch_data
        }

        for future in concurrent.futures.as_completed(future_to_gif):
            gif_data = future_to_gif[future]
            try:
                result = future.result()
                if result:
                    completed_count += 1
                    if completed_count % 10 == 0:
                        logger.info(f"Progress: {completed_count}/{len(batch_data)} GIFs processed")
            except Exception as e:
                logger.error(f"Error processing {gif_data['name']}: {e}")

    return completed_count

def _process_single_gif_worker(gif_data):
    """
    Worker function for processing a single GIF in a separate process
    """
    try:
        return _process_single_gif(
            gif_data['source_path'],
            gif_data['output_path'],
            gif_data['accent_color'],
            gif_data['name']
        )
    except Exception as e:
        logger.error(f"Worker error for {gif_data['name']}: {e}")
        return False

def _process_single_gif(input_path, output_path, accent_color, gif_name):
    """
    Process a single GIF with hash-based caching
    """
    # Check if we need to regenerate
    if os.path.exists(output_path):
        source_hash = _calculate_gif_hash(input_path)
        existing_hash = _get_stored_hash(gif_name, os.path.dirname(output_path))

        if source_hash and existing_hash and source_hash == existing_hash:
            logger.debug(f"Using cached: {os.path.basename(output_path)}")
            return True

    # Process the GIF
    return _apply_color_to_gif(input_path, output_path, accent_color, gif_name)

def _apply_color_to_gif(input_path, output_path, accent_color, gif_name):
    """
    Apply color transformation to GIF
    """
    start_time = time.time()

    try:
        # Parse target color
        target_rgb = tuple(int(accent_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
        target_h, target_s, target_v = _rgb_to_hsv(*target_rgb)

        with Image.open(input_path) as gif:
            # Extract all frames
            frames = []
            frame_durations = []
            original_info = gif.info.copy()
            try:
                while True:
                    frame = gif.copy().convert('RGBA')
                    frames.append(frame)
                    frame_durations.append(gif.info.get('duration', 100))
                    gif.seek(gif.tell() + 1)
            except EOFError:
                pass

            if not frames:
                return False

            processed_frames = _process_frames(frames, target_h, target_s, target_v)

            _save_gif(processed_frames, frame_durations, original_info, output_path)

            # Store hash for this GIF in temporary storage
            _store_temp_hash(gif_name, input_path, os.path.dirname(output_path))

            elapsed = time.time() - start_time
            if elapsed > 0.5:
                logger.debug(f"Colorized {os.path.basename(input_path)}: {elapsed:.3f}s")

            return True

    except Exception as e:
        logger.error(f"Error processing {input_path}: {e}")
        # Fallback: copy original
        try:
            shutil.copy2(input_path, output_path)
            logger.info(f"Fallback copy created for: {os.path.basename(input_path)}")
            return True
        except Exception as copy_error:
            logger.error(f"Fallback copy also failed for {input_path}: {copy_error}")
            return False

def _load_hashes(output_dir):
    """Load existing hashes from hashes.json"""
    hashes_path = os.path.join(output_dir, "hashes.json")
    if os.path.exists(hashes_path):
        try:
            with open(hashes_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load hashes.json: {e}")
    return {}

def _write_hashes_file(output_dir):
    """Write hashes.json"""
    hashes_path = os.path.join(output_dir, "hashes.json")
    try:
        # Collect all temporary hashes
        final_hashes = {}
        for filename in os.listdir(output_dir):
            if filename.endswith('.gif'):
                gif_name = filename
                hash_file = os.path.join(output_dir, f".{gif_name}.hash")
                if os.path.exists(hash_file):
                    try:
                        with open(hash_file, 'r') as f:
                            final_hashes[gif_name] = f.read().strip()
                        # Clean up temp hash file
                        os.remove(hash_file)
                    except Exception as e:
                        logger.warning(f"Could not read hash for {gif_name}: {e}")

        # Write final hashes.json
        with open(hashes_path, 'w') as f:
            json.dump(final_hashes, f, indent=2)
        logger.info(f"Saved {len(final_hashes)} hashes to {hashes_path}")

    except Exception as e:
        logger.error(f"Could not write hashes.json: {e}")

def _store_temp_hash(gif_name, input_path, output_dir):
    """Store hash temporarily in individual files to avoid read/write conflicts"""
    try:
        source_hash = _calculate_gif_hash(input_path)
        if source_hash:
            hash_file = os.path.join(output_dir, f".{gif_name}.hash")
            with open(hash_file, 'w') as f:
                f.write(source_hash)
    except Exception as e:
        logger.warning(f"Could not store temp hash for {gif_name}: {e}")

def _get_stored_hash(gif_name, output_dir):
    """Get stored hash from temporary file"""
    hash_file = os.path.join(output_dir, f".{gif_name}.hash")
    if os.path.exists(hash_file):
        try:
            with open(hash_file, 'r') as f:
                return f.read().strip()
        except Exception:
            pass
    return None

def _calculate_gif_hash(file_path):
    """Calculate SHA256 hash of a GIF file"""
    try:
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        logger.error(f"Error calculating hash for {file_path}: {e}")
        return None

def _should_regenerate_gif(input_path, output_path, gif_name, existing_hashes):
    """Check if we need to regenerate the colorized GIF"""
    if not os.path.exists(output_path):
        return True

    if not os.path.exists(input_path):
        return False

    current_hash = _calculate_gif_hash(input_path)
    if not current_hash:
        return True

    existing_hash = existing_hashes.get(gif_name)
    if not existing_hash or existing_hash != current_hash:
        return True

    return False

def _process_frames(frames, target_h, target_s, target_v):
    """Process all frames with color transformation"""
    processed_frames = []

    for frame in frames:
        img_array = np.array(frame, dtype=np.float32)
        processed_array = _apply_color_transform(img_array, target_h, target_s, target_v)
        processed_frames.append(Image.fromarray(processed_array.astype(np.uint8), 'RGBA'))

    return processed_frames

def _apply_color_transform(img_array, target_h, target_s, target_v):
    """Apply color transformation to image array"""
    # Extract channels
    r, g, b, a = img_array[..., 0], img_array[..., 1], img_array[..., 2], img_array[..., 3]

    # Calculate colorfulness (std dev) for each pixel
    rgb_mean = (r + g + b) / 3.0
    rgb_std = np.sqrt(((r - rgb_mean)**2 + (g - rgb_mean)**2 + (b - rgb_mean)**2) / 3.0)

    # Create mask for colored pixels
    colored_mask = (a > 10) & (rgb_std > 5)

    if not np.any(colored_mask):
        return img_array  # No colored pixels to process

    # Extract colored pixels
    colored_pixels = img_array[colored_mask]
    colored_rgb = colored_pixels[:, :3]

    # Convert colored RGB to HSV
    colored_hsv = _rgb_to_hsv_batch(colored_rgb)

    # Calculate average saturation and value
    avg_s = np.mean(colored_hsv[:, 1])
    avg_v = np.mean(colored_hsv[:, 2])

    # Avoid division by zero
    avg_s = max(avg_s, 0.001)
    avg_v = max(avg_v, 0.001)

    # Apply transformations
    new_h = np.full(colored_hsv.shape[0], target_h)
    new_s = np.clip(colored_hsv[:, 1] * (target_s / avg_s), 0.0, 1.0)
    new_v = np.clip(colored_hsv[:, 2] * (target_v / avg_v), 0.0, 1.0)

    # Convert back to RGB
    new_rgb = _hsv_to_rgb_batch(new_h, new_s, new_v)

    # Update the colored pixels
    result_array = img_array.copy()
    result_array[colored_mask, :3] = new_rgb

    return result_array

def _rgb_to_hsv_batch(rgb_array):
    """Convert RGB to HSV for batch of pixels"""
    r, g, b = rgb_array[..., 0], rgb_array[..., 1], rgb_array[..., 2]
    r, g, b = r/255.0, g/255.0, b/255.0

    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    df = mx - mn

    h = np.zeros_like(mx)
    s = np.zeros_like(mx)
    v = mx

    # Avoid division by zero
    df_nonzero = df != 0

    # Calculate hue
    mask_r = (mx == r) & df_nonzero
    mask_g = (mx == g) & df_nonzero
    mask_b = (mx == b) & df_nonzero

    h[mask_r] = (60 * ((g[mask_r] - b[mask_r]) / df[mask_r]) + 360) % 360
    h[mask_g] = (60 * ((b[mask_g] - r[mask_g]) / df[mask_g]) + 120) % 360
    h[mask_b] = (60 * ((r[mask_b] - g[mask_b]) / df[mask_b]) + 240) % 360

    # Calculate saturation
    s[mx != 0] = df[mx != 0] / mx[mx != 0]

    return np.stack([h, s, v], axis=-1)

def _hsv_to_rgb_batch(h, s, v):
    """Convert HSV to RGB for batch of pixels"""
    h = h % 360
    hi = (h / 60).astype(int) % 6
    f = (h / 60) - (h / 60).astype(int)

    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)

    # Initialize result arrays
    r = np.zeros_like(h)
    g = np.zeros_like(h)
    b = np.zeros_like(h)

    # Assign based on hue segment
    masks = [hi == i for i in range(6)]
    conditions = [
        (v, t, p),    # hi == 0
        (q, v, p),    # hi == 1
        (p, v, t),    # hi == 2
        (p, q, v),    # hi == 3
        (t, p, v),    # hi == 4
        (v, p, q)     # hi == 5
    ]

    for i, (rr, gg, bb) in enumerate(conditions):
        mask = masks[i]
        r[mask] = rr[mask]
        g[mask] = gg[mask]
        b[mask] = bb[mask]

    # Scale to 0-255 and stack
    rgb = np.stack([r * 255, g * 255, b * 255], axis=-1)
    return np.clip(rgb, 0, 255).astype(np.float32)

def _rgb_to_hsv(r, g, b):
    """Convert single RGB pixel to HSV"""
    r, g, b = r/255.0, g/255.0, b/255.0
    mx = max(r, g, b)
    mn = min(r, g, b)
    df = mx - mn

    if mx == mn:
        h = 0.0
    elif mx == r:
        h = (60 * ((g - b) / df) + 360) % 360
    elif mx == g:
        h = (60 * ((b - r) / df) + 120) % 360
    elif mx == b:
        h = (60 * ((r - g) / df) + 240) % 360
    else:
        h = 0.0

    s = 0.0 if mx == 0 else df / mx
    v = mx
    return (h, s, v)

def _save_gif(frames, durations, gif_info, output_path):
    """Save frames as GIF"""
    if frames:
        frames[0].save(
            output_path,
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=gif_info.get('loop', 0),
            optimize=True,
            disposal=2
        )

def _update_color_symlinks(gif_list, accent_color, color_subdir, output_dir):
    """Update all symlinks to point to current colorized versions"""
    logger.info("Updating symlinks to current color...")
    successful_links = 0

    for gif_name in gif_list:
        colorized_path = os.path.join(color_subdir, gif_name)
        symlink_path = os.path.join(output_dir, gif_name)

        if os.path.exists(colorized_path):
            if _create_color_symlink(colorized_path, symlink_path):
                successful_links += 1
        else:
            logger.warning(f"Colorized file not found for {gif_name}")

    logger.info(f"Symlink update complete: {successful_links}/{len(gif_list)} links created")

def _create_color_symlink(target_path, symlink_path):
    """Create symlink pointing to colorized file"""
    try:
        if os.path.exists(symlink_path) or os.path.islink(symlink_path):
            os.remove(symlink_path)

        # Create relative symlink
        target_rel = os.path.relpath(target_path, os.path.dirname(symlink_path))
        os.symlink(target_rel, symlink_path)
        return True
    except Exception as e:
        logger.warning(f"Symlink failed for {os.path.basename(symlink_path)}: {e}")
        try:
            shutil.copy2(target_path, symlink_path)
            return True
        except Exception as copy_error:
            logger.error(f"File copy also failed: {copy_error}")
            return False

def _find_gif_source(input_dirs, gif_name):
    """Find which input directory contains the GIF file"""
    for input_dir in input_dirs:
        potential_path = os.path.join(input_dir, gif_name)
        if os.path.exists(potential_path):
            return input_dir
    return None
