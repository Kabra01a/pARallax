// @refresh reset
import React, { useState, useEffect } from "react";
import { View, Animated, StyleSheet } from "react-native";
import Svg, { Circle } from "react-native-svg";
import * as Haptics from "expo-haptics";

const AnimatedCircle = Animated.createAnimatedComponent(Circle);

const numX = 4;
const numY = 5;
const total = numX * numY;
const BASE_DURATION = 400;
const RANDOM_DURATION = 300;

const styles = StyleSheet.create({
  container: {
    ...StyleSheet.absoluteFillObject,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(0, 0, 0, 0.2)",
  },
});

export default function ProgressIndicator() {
  // Initialize animation values
  const init = Array(total)
    .fill(1)
    .map(() => ({
      r: new Animated.Value(1),
      a: new Animated.Value(1),
    }));
  const [anim] = useState(init);

  useEffect(() => {
    console.log("Initializing progress animation...");
    let isActive = true;

    const triggerHaptic = async () => {
      try {
        await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
      } catch (error) {
        console.log("Haptic feedback not available");
      }
    };

    const animations = anim.map((v, i) => {
      const duration = BASE_DURATION + Math.random() * RANDOM_DURATION;

      const seq = Animated.parallel([
        Animated.sequence([
          Animated.timing(anim[i].r, {
            toValue: 3,
            duration: duration - 50,
            useNativeDriver: true,
            isInteraction: false,
          }),
          Animated.timing(anim[i].r, {
            toValue: 1,
            duration: duration,
            useNativeDriver: true,
            isInteraction: false,
          }),
        ]),
        Animated.sequence([
          Animated.timing(anim[i].a, {
            toValue: 0.1,
            duration: duration - 50,
            useNativeDriver: true,
            isInteraction: false,
          }),
          Animated.timing(anim[i].a, {
            toValue: 1,
            duration: duration,
            useNativeDriver: true,
            isInteraction: false,
          }),
        ]),
      ]);

      return Animated.loop(seq);
    });

    const masterAnimation = Animated.stagger(50, animations);
    masterAnimation.start();

    const hapticInterval = setInterval(triggerHaptic, 1000);

    return () => {
      isActive = false;
      clearInterval(hapticInterval);
      animations.forEach((anim) => anim.stop());
      console.log("Cleaning up progress animation...");
    };
  }, []);

  const circles = [];
  const margin = 100 / numX;
  for (let x = 0; x < numX; x++) {
    for (let y = 0; y < numY; y++) {
      const i = y * numX + x;
      circles.push({
        x: (x + 0.5) * margin,
        y: y * margin,
        r: anim[i].r,
        a: anim[i].a,
      });
    }
  }

  return (
    <View style={styles.container}>
      <Svg height="100%" width="100%" viewBox="0 0 100 100">
        {circles.map((c, index) => (
          <AnimatedCircle
            key={`circle-${index}`}
            cx={c.x}
            cy={c.y}
            r={c.r}
            fill="white"
            opacity={c.a}
          />
        ))}
      </Svg>
    </View>
  );
}
