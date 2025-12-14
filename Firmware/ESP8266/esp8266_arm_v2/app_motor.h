#ifndef APP_MOTOR_H
#define APP_MOTOR_H

void app_motor_init();
void app_motor_update(); // Call in loop()
void app_motor_set_target(float x, float y, float z, float gripper);
void app_motor_set_angles(float base, float shoulder, float elbow, float gripper);
void app_motor_stop();
bool app_motor_is_moving();

#endif
