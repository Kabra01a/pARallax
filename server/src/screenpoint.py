"""Locate a camera view within a screenshot.

Given a photo of a monitor (the "view") and a screenshot of that same monitor
(the "screen"), estimate where the centre of the view falls in screen space.

Approach: SIFT keypoints -> FLANN matching -> Lowe ratio test -> RANSAC
homography -> perspective-transform the view centre.

This replaces the upstream `screenpoint` package, which is unmaintained.
Known weakness: SIFT degrades on low-texture screens and steep viewing angles.
Learned matchers (LightGlue / LoFTR) are the planned upgrade - see README.
"""

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Lowe's ratio test threshold. Lower = stricter = fewer but better matches.
RATIO_TEST_THRESHOLD = 0.7

# Minimum good matches before attempting a homography (cv2 needs >= 4).
MIN_MATCH_COUNT = 10

# RANSAC reprojection tolerance, in pixels.
RANSAC_REPROJ_THRESHOLD = 5.0

NOT_FOUND = (-1, -1)


def project(view_arr: np.ndarray, screen_arr: np.ndarray):
    """Return (x, y) of the view centre in screen coordinates, or (-1, -1).

    Both inputs must be single-channel (grayscale) arrays.
    """
    try:
        view = view_arr.astype(np.uint8)
        screen = screen_arr.astype(np.uint8)

        sift = cv2.SIFT_create()
        kp_view, des_view = sift.detectAndCompute(view, None)
        kp_screen, des_screen = sift.detectAndCompute(screen, None)

        if des_view is None or des_screen is None:
            logger.debug("no descriptors found")
            return NOT_FOUND
        if len(des_view) < 2 or len(des_screen) < 2:
            logger.debug("too few descriptors: view=%d screen=%d", len(des_view), len(des_screen))
            return NOT_FOUND

        flann = cv2.FlannBasedMatcher(
            dict(algorithm=1, trees=5),  # FLANN_INDEX_KDTREE
            dict(checks=50),
        )
        matches = flann.knnMatch(des_view, des_screen, k=2)

        good = [m for pair in matches if len(pair) == 2
                for m, n in [pair] if m.distance < RATIO_TEST_THRESHOLD * n.distance]

        if len(good) < MIN_MATCH_COUNT:
            logger.debug("only %d good matches (need %d)", len(good), MIN_MATCH_COUNT)
            return NOT_FOUND

        src = np.float32([kp_view[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst = np.float32([kp_screen[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

        homography, inlier_mask = cv2.findHomography(
            src, dst, cv2.RANSAC, RANSAC_REPROJ_THRESHOLD
        )
        if homography is None:
            logger.debug("homography estimation failed")
            return NOT_FOUND

        inliers = int(inlier_mask.sum()) if inlier_mask is not None else 0
        logger.debug("matched %d/%d inliers", inliers, len(good))
        if inliers < MIN_MATCH_COUNT:
            return NOT_FOUND

        height, width = view.shape[:2]
        centre = np.float32([[width / 2, height / 2]]).reshape(-1, 1, 2)
        projected = cv2.perspectiveTransform(centre, homography)

        x, y = int(projected[0][0][0]), int(projected[0][0][1])

        # Reject matches that land outside the screen entirely.
        screen_h, screen_w = screen.shape[:2]
        if not (0 <= x < screen_w and 0 <= y < screen_h):
            logger.debug("projected point (%d, %d) outside screen %dx%d", x, y, screen_w, screen_h)
            return NOT_FOUND

        return x, y

    except cv2.error as exc:
        logger.debug("OpenCV error during projection: %s", exc)
        return NOT_FOUND
