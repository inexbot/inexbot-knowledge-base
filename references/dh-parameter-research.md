# DH 参数与正运动学（FK）研究成果

从纳博特开放平台（open.inexbot.com）知识库中检索提取。关于纳博特机器人 DH 参数的布局、约定和问题。

---

## 1. RobotDHParam 结构体 — L1-L20 字段布局

对于六轴串联机器人（robotType=1），文档中仅定义了 **L1-L8**：

| 字段 | 类型 | 说明 |
|------|------|------|
| L1 | double | L1杆长，范围[-4000,4000] |
| L2 | double | L2杆长，范围[-4000,4000] |
| L3 | double | L3杆长，范围[-4000,4000] |
| L4 | double | L4杆长，范围[-4000,4000] |
| L5 | double | L5杆长，范围[-4000,4000] |
| L6 | double | L6杆长，范围[-4000,4000] |
| L7 | double | L7杆长，范围[-4000,4000] |
| L8 | double | L8杆长，范围[-4000,4000] |
| couplingRatio12~56 | double | 耦合比参数 |
| threeAxisDirection | double | 三轴方向，范围 -90, 0 度 |
| fiveAxisDirection | double | 五轴方向，范围 0, 90 度 |
| mountAngle | bool | 机器人正装或倒装 |
| angleToDistance | array[6] | 角度转距离列表 |
| distanceToAngle | array[6] | 距离转角度列表 |
| dynamicLimit | object | J2+J3 范围限制 |

**关键发现**：
- L1-L8 全部标注为「杆长」，**没有区分 a（连杆长度）、d（连杆偏距）、α（扭转角）**
- θ_offset（关节零偏）**不在 DH 参数中**，通过 `Joint` 数组的 `direction`（模型方向）和 `axisDirection`（关节实际方向）体现
- L9-L20 对 6 轴关节机器人无文档说明
- 实际值示例（六轴串联机器人）：
  ```
  L1=390.0, L2=450.872, L3=99.462, L4=471.29, L5=123.0, L6=-0.544, L7=-0.0, L8=0.0
  ```

---

## 2. DH 约定 — Standard DH vs Modified DH

**文档未明确说明**。从 `Joint` 参数结构可推断：

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| direction | int | -1.0 | 模型方向，范围[-1,1] |
| axisDirection | int | 1 | 关节实际方向，范围[-1,1] |

这两个字段的组合决定各关节运动方向的正负符号，这是 Standard DH 和 Modified DH 的核心差异之一，但文档未给出 FK 矩阵构建顺序或约定说明。

---

## 3. α（扭转角）存储位置

对于标准六轴关节机器人，腕部 J4/J5/J6 通常应有 ±90° 扭转角。

但文档中：
- **L13-L18 全为 0**，不是扭转角存储位置
- 扭转角信息通过 `threeAxisDirection`（三轴方向，默认 -90.0°）和 `fiveAxisDirection`（五轴方向，默认 90.0°）体现，这两个字段**明确使用度为单位**，取值为 -90°、0°、90° 等离散值

**结论**：α 值不在 L13-L18 中，而是通过 threeAxisDirection / fiveAxisDirection 处理。

---

## 4. 正运动学（FK）计算

**文档中未找到 FK 计算公式**。检索覆盖范围：
- DH参数 JSON 协议（命令字 0x20C0-0x20D2）
- 机器人关节参数（命令字 0x20C5-0x20C6）
- 标定协议（命令字 0x3700-0x3739）
- 控制器二次开发 API
- 工具手标定

所有文档均**没有**给出：
- L 字段与 a/d/α/θ 的映射表
- FK 矩阵乘法顺序（Standard DH 或 Modified DH）
- θ_offset 字段位置

---

## 5. 行动建议

1. **联系纳博特技术支持**：获取 `RobotDHParam` 结构体完整说明和 FK 计算公式（官网 https://www.inexbot.com）
2. **反推法实测**：调用 `get_origin_coord_to_target_coord_robot` 接口在不同关节角度下获取末端位姿，结合已知 L1-L8 值，用优化方法反推 DH 参数映射
3. **检查 SDK 头文件**：如有 NRC SDK 头文件（如 `nrcAPI.h` 或 `RobotKinematics.h`），结构体定义注释可能比文档更详细

---

## 相关命令字

| 操作 | 命令字 |
|------|--------|
| 上位机查询 DH 参数 | 0x20C0 |
| 上位机设置 DH 参数 | 0x20C1 |
| 上位机查询机器人关节参数 | 0x20C6 |
| 上位机查询机器人笛卡尔参数 | 0x20C9 |
| 上位机查询预置机器人参数 | 0x20D2 |

---

## 引用来源

- [DH参数 - 纳博特开放平台](https://open.inexbot.com/07.JSON%20%E5%8D%8F%E8%AE%AE/02.RTL-24.03/02.%E6%9C%BA%E5%99%A8%E4%BA%BA/01.%E5%8F%82%E6%95%B0%E8%AE%BE%E7%BD%AE/01.DH%E5%8F%82%E6%95%B0)
- [标定 - 纳博特开放平台](https://open.inexbot.com/07.JSON%20%E5%8D%8F%E8%AE%AE/02.RTL-24.03/02.%E6%9C%BA%E5%99%A8%E4%BA%BA/08.%E6%A0%87%E5%AE%9A)
- [机器人关节参数 - 纳博特开放平台](https://open.inexbot.com/07.JSON%20%E5%8D%8F%E8%AE%AE/02.RTL-24.03/02.%E6%9C%BA%E5%99%A8%E4%BA%BA/01.%E5%8F%82%E6%95%B0%E8%AE%BE%E7%BD%AE/01.DH%E5%8F%82%E6%95%B0)