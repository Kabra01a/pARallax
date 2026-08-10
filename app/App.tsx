import React, { useState, useEffect, useRef } from "react";
import {
  StyleSheet,
  View,
  TouchableWithoutFeedback,
  Image,
  Alert,
} from "react-native";
import { Camera, CameraType } from "expo-camera";
import * as ImageManipulator from "expo-image-manipulator";
import * as Haptics from "expo-haptics";
import ProgressIndicator from "./components/ProgressIndicator";
import Server from "./components/Server";

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "black",
  },
  camera: {
    flex: 1,
  },
  resultContainer: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 200,
  },
  resultImage: {
    position: "absolute",
    zIndex: 300,
    top: "25%",
    left: 0,
    width: "100%",
    height: "50%",
  },
});

export default function App() {
  const [hasPermission, setHasPermission] = useState<boolean | null>(null);
  const [pressed, setPressed] = useState(false);
  const [pasting, setPasting] = useState(false);
  const [currentImage, setCurrentImage] = useState<string>("");
  const cameraRef = useRef<Camera | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const { status } = await Camera.requestCameraPermissionsAsync();
        setHasPermission(status === "granted");

        if (status !== "granted") {
          Alert.alert(
            "Permission Required",
            "Camera permission is required to use this app."
          );
          return;
        }

        await Server.ping();
        console.log("Server connected successfully");
      } catch (error) {
        console.error("Initialization error:", error);
        Alert.alert(
          "Server Error",
          "Could not connect to server. Please check if server is running."
        );
      }
    })();
  }, []);

  const cut = async () => {
    if (!cameraRef.current) return;

    try {
      await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);

      console.log("Taking picture...");
      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.7,
        skipProcessing: true,
      });

      console.log("Resizing image...");
      const resized = await ImageManipulator.manipulateAsync(
        photo.uri,
        [
          { resize: { width: 256, height: 512 } },
          { crop: { originX: 0, originY: 128, width: 256, height: 256 } },
        ],
        { compress: 0.7, format: ImageManipulator.SaveFormat.JPEG }
      );

      const result = await Server.cut(resized.uri);
      setCurrentImage(result);

      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } catch (error) {
      console.error("Cut error:", error);
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      Alert.alert("Error", "Failed to process image. Please try again.");
    }
  };

  const paste = async () => {
    if (!cameraRef.current) return;

    try {
      console.log("Taking picture for paste...");
      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.7,
        skipProcessing: true,
      });

      console.log("Resizing image...");
      const resized = await ImageManipulator.manipulateAsync(
        photo.uri,
        [{ resize: { width: 350, height: 700 } }],
        { compress: 0.7, format: ImageManipulator.SaveFormat.JPEG }
      );

      const result = await Server.paste(resized.uri);

      if (result.status === "screen not found") {
        await Haptics.notificationAsync(
          Haptics.NotificationFeedbackType.Warning
        );
        Alert.alert(
          "Not Found",
          "Could not locate screen position. Please ensure Photoshop window is visible."
        );
      } else {
        await Haptics.notificationAsync(
          Haptics.NotificationFeedbackType.Success
        );
      }
    } catch (error) {
      console.error("Paste error:", error);
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      Alert.alert("Error", "Failed to paste image. Please try again.");
    }
  };

  const handlePressIn = () => {
    setPressed(true);
    cut();
  };

  const handlePressOut = () => {
    setPressed(false);
    setPasting(true);
    paste().finally(() => {
      setCurrentImage("");
      setPasting(false);
    });
  };

  if (hasPermission === null) {
    return <View />;
  }
  if (hasPermission === false) {
    return <View style={styles.container} />;
  }

  return (
    <View style={styles.container}>
      <Camera
        ref={cameraRef}
        style={styles.camera}
        ratio="16:9"
        type={CameraType.back}
      >
        <TouchableWithoutFeedback
          onPressIn={handlePressIn}
          onPressOut={handlePressOut}
        >
          <View style={StyleSheet.absoluteFill} />
        </TouchableWithoutFeedback>

        {/* Show loading animation when processing */}
        {(pressed && !currentImage) || pasting ? <ProgressIndicator /> : null}

        {pressed && currentImage ? (
          <View style={styles.resultContainer}>
            <Image
              style={styles.resultImage}
              source={{ uri: currentImage }}
              resizeMode="contain"
            />
          </View>
        ) : null}
      </Camera>
    </View>
  );
}
