#!/usr/bin/env python3
"""
批量处理广西、广东、贵州申论 PDF，提取全文生成 ShenlunAI 格式 JSON。
支持 多省联考 格式（广西、贵州）和 广东省考 格式。
处理完成后自动运行 fix_essay_fields 和 fix_scores 修正大作文和分值。
"""
import json
import os
import re
import subprocess
import sys
import unicodedata
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message=".*FontBBox.*")
try:
    import pdfplumber
except ImportError:
    print("请先安装: pip install pdfplumber")
    sys.exit(1)

# 路径
BASE = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE / "data"
SHENLUN_BASE = Path("/Users/luzhipeng/Documents/学习及生活/申论")

# 区域配置: (PDF目录, 区域名, 文件名->输出ID映射)
REGIONS = {
    "北京": (
        SHENLUN_BASE / "北京",
        "北京",
        {
            "2018年北京市公考《申论》题.pdf": "gwy_beijing_2018",
            "2019年北京市公考《申论》题.pdf": "gwy_beijing_2019",
            "2020年北京市公考《申论》题（乡镇）.pdf": "gwy_beijing_2020_XiangZhen",
            "2020年北京市公考《申论》题（区级）.pdf": "gwy_beijing_2020_district",
            "2021年北京市公考《申论》题（乡镇）.pdf": "gwy_beijing_2021_XiangZhen",
            "2021年北京市公考《申论》题（区级）.pdf": "gwy_beijing_2021_district",
            "2022年北京市公考《申论》题.pdf": "gwy_beijing_2022",
            "2023年北京市公考《申论》题.pdf": "gwy_beijing_2023",
            "2024年北京市公考《申论》题.pdf": "gwy_beijing_2024",
            "2025年北京市公考《申论》题.pdf": "gwy_beijing_2025_A",
        },
    ),
    "吉林": (
        SHENLUN_BASE / "吉林",
        "吉林",
        {
            "2023年公务员多省联考《申论》题（吉林乙卷）.pdf": "gwy_jilin_2023_B",
        },
    ),
    "国家": (
        SHENLUN_BASE / "国家",
        "国家",
        {
            "2018年国家公考《申论》题（副省级）.pdf": "gwy_guojia_2018_Fushengji",
            "2018年国家公考《申论》题（地市级）.pdf": "gwy_guojia_2018_Dishiji",
            "2019年国家公考《申论》题（副省级）.pdf": "gwy_guojia_2019_Fushengji",
            "2019年国家公考《申论》题（地市级）.pdf": "gwy_guojia_2019_Dishiji",
            "2020年国家公考《申论》题（副省级）.pdf": "gwy_guojia_2020_Fushengji",
            "2020年国家公考《申论》题（地市级）.pdf": "gwy_guojia_2020_Dishiji",
            "2021年国家公考《申论》题（副省级）.pdf": "gwy_guojia_2021_Fushengji",
            "2021年国家公考《申论》题（地市级）.pdf": "gwy_guojia_2021_Dishiji",
            "2022年国家公考《申论》题（副省级）.pdf": "gwy_guojia_2022_Fushengji",
            "2022年国家公考《申论》题（地市级）.pdf": "gwy_guojia_2022_Dishiji",
            "2022年国家公考《申论》题（行政执法）.pdf": "gwy_guojia_2022_Xingzhengzhifa",
            "2023年国家公考《申论》题（副省级）.pdf": "gwy_guojia_2023_Fushengji",
            "2023年国家公考《申论》题（地市级）.pdf": "gwy_guojia_2023_Dishiji",
            "2023年国家公考《申论》题（行政执法）.pdf": "gwy_guojia_2023_Xingzhengzhifa",
            "2024年国家公考《申论》题（副省级）.pdf": "gwy_guojia_2024_Fushengji",
            "2024年国家公考《申论》题（地市级）.pdf": "gwy_guojia_2024_Dishiji",
            "2024年国家公考《申论》题（行政执法）.pdf": "gwy_guojia_2024_Xingzhengzhifa",
            "2025年国家公考《申论》题（副省级）.pdf": "gwy_guojia_2025_Fushengji",
            "2025年国家公考《申论》题（地市级）.pdf": "gwy_guojia_2025_Dishiji",
            "2025年国家公考《申论》题（行政执法）.pdf": "gwy_guojia_2025_Xingzhengzhifa",
            "2026年国家公考《申论》题（副省级）（网友回忆版）.pdf": "gwy_guojia_2026_fusheng",
            "2026年国家公考《申论》题（行政执法）（网友回忆版）.pdf": "gwy_guojia_2026_xingzhengzhifa",
        },
    ),
    "安徽": (
        SHENLUN_BASE / "安徽",
        "安徽",
        {
            "2018年公务员多省联考《申论》题（安徽A、普通选调卷）.pdf": "gwy_anhui_2018_A",
            "2018年公务员多省联考《申论》题（安徽B卷）.pdf": "gwy_anhui_2018_B",
            "2019年公务员多省联考《申论》题（安徽A、普通选调卷）.pdf": "gwy_anhui_2019_A",
            "2019年公务员多省联考《申论》题（安徽B卷）.pdf": "gwy_anhui_2019_B",
            "2020年0822公务员多省联考《申论》题（安徽A、普通选调卷）.pdf": "gwy_anhui_2020_A",
            "2020年0822公务员多省联考《申论》题（安徽B卷）.pdf": "gwy_anhui_2020_B",
            "2020年0822公务员多省联考《申论》题（安徽C卷）.pdf": "gwy_anhui_2020_C",
            "2021年公务员多省联考《申论》题（安徽A、普通选调卷）.pdf": "gwy_anhui_2021_A",
            "2021年公务员多省联考《申论》题（安徽B卷）.pdf": "gwy_anhui_2021_B",
            "2021年公务员多省联考《申论》题（安徽C卷）.pdf": "gwy_anhui_2021_C",
            "2022年公务员多省联考《申论》题（安徽A、普通选调卷）.pdf": "gwy_anhui_2022_A",
            "2022年公务员多省联考《申论》题（安徽B卷）.pdf": "gwy_anhui_2022_B",
            "2022年公务员多省联考《申论》题（安徽C卷）.pdf": "gwy_anhui_2022_C",
            "2023年公务员多省联考《申论》题（安徽A、普通选调卷）.pdf": "gwy_anhui_2023_A",
            "2023年公务员多省联考《申论》题（安徽B卷）.pdf": "gwy_anhui_2023_B",
            "2023年公务员多省联考《申论》题（安徽C卷）.pdf": "gwy_anhui_2023_C",
            "2023年安徽省乡镇机关专项考试《申论》题.pdf": "gwy_anhui_2023_township",
            "2024年公务员多省联考《申论》题（安徽B卷）.pdf": "gwy_anhui_2024_B",
            "2024年公务员多省联考《申论》题（安徽C卷）.pdf": "gwy_anhui_2024_C",
            "2025年公务员多省联考《申论》题（安徽A、普通选调卷）.pdf": "gwy_anhui_2025_A",
            "2025年公务员多省联考《申论》题（安徽B卷）.pdf": "gwy_anhui_2025_B",
            "2025年公务员多省联考《申论》题（安徽C卷）.pdf": "gwy_anhui_2025_C",
        },
    ),
    "河南": (
        SHENLUN_BASE / "河南",
        "河南",
        {
            "2017年河南省公考 《申论》题.pdf": "gwy_henan_2017",
            "2019年公务员多省联考《申论》题（河南乡镇卷）.pdf": "gwy_henan_2019_XiangZhen",
            "2019年公务员多省联考《申论》题（河南县级、普通选调卷）.pdf": "gwy_henan_2019_XianJi",
            "2020年0725公务员多省联考《申论》题（河南乡镇卷）.pdf": "gwy_henan_2020_XiangZhen",
            "2020年0725公务员多省联考《申论》题（河南县级卷）.pdf": "gwy_henan_2020_XianJi",
            "2021年公务员多省联考《申论》题（河南乡镇卷）.pdf": "gwy_henan_2021_XiangZhen",
            "2021年公务员多省联考《申论》题（河南县级卷）.pdf": "gwy_henan_2021_XianJi",
            "2022年公务员多省联考《申论》题（河南乡镇卷）.pdf": "gwy_henan_2022_XiangZhen",
            "2022年公务员多省联考《申论》题（河南县级卷）.pdf": "gwy_henan_2022_XianJi",
            "2023年公务员多省联考《申论》题（河南县级卷）.pdf": "gwy_henan_2023_XianJi",
            "2023年公务员多省联考《申论》题（河南市级卷）.pdf": "gwy_henan_2023_ShiJi",
            "2024年公务员多省联考《申论》题（河南县级卷）.pdf": "gwy_henan_2024_XianJi",
            "2024年公务员多省联考《申论》题（河南市级卷）.pdf": "gwy_henan_2024_ShiJi",
            "2025年公务员多省联考《申论》题（河南县级卷）（网友回忆版）.pdf": "gwy_henan_2025_XianJi",
            "2025年公务员多省联考《申论》题（河南市级卷）.pdf": "gwy_henan_2025_ShiJi",
        },
    ),
    "海南": (
        SHENLUN_BASE / "海南",
        "海南",
        {
            "2017年公务员多省联考《申论》题（海南卷）.pdf": "gwy_hainan_2017",
            "2018年公务员多省联考《申论》题（海南卷）.pdf": "gwy_hainan_2018",
            "2019年公务员多省联考《申论》题（海南乡镇卷）.pdf": "gwy_hainan_2019_XiangZhen",
            "2019年公务员多省联考《申论》题（海南县级卷）.pdf": "gwy_hainan_2019_XianJi",
            "2020年0822公务员多省联考《申论》题（海南乡镇卷）.pdf": "gwy_hainan_2020_XiangZhen",
            "2020年0822公务员多省联考《申论》题（海南县级卷）.pdf": "gwy_hainan_2020_XianJi",
            "2021年公务员多省联考《申论》题（海南乡镇卷）.pdf": "gwy_hainan_2021_XiangZhen",
            "2021年公务员多省联考《申论》题（海南县级卷）.pdf": "gwy_hainan_2021_XianJi",
            "2022年公务员多省联考《申论》题（海南B卷）.pdf": "gwy_hainan_2022_B",
            "2022年公务员多省联考《申论》题（海南C卷）.pdf": "gwy_hainan_2022_C",
            "2023年公务员多省联考《申论》题（海南A卷）.pdf": "gwy_hainan_2023_A",
            "2023年公务员多省联考《申论》题（海南B卷）.pdf": "gwy_hainan_2023_B",
            "2023年公务员多省联考《申论》题（海南C卷）.pdf": "gwy_hainan_2023_C",
            "2024年公务员多省联考《申论》题（海南A卷）.pdf": "gwy_hainan_2024_A",
            "2025年公务员多省联考《申论》题（海南B卷）.pdf": "gwy_hainan_2025_B",
        },
    ),
    "甘肃": (
        SHENLUN_BASE / "甘肃",
        "甘肃",
        {
            "2018年公务员多省联考《申论》题（甘肃卷）.pdf": "gwy_gansu_2018_General",
            "2019年甘肃省公考《申论》题.pdf": "gwy_gansu_2019_General",
            "2020年0822公务员多省联考《申论》题（甘肃乡镇卷）.pdf": "gwy_gansu_2020_XiangZhen",
            "2020年0822公务员多省联考《申论》题（甘肃市县卷）.pdf": "gwy_gansu_2020_ShiXian",
            "2020年0822公务员多省联考《申论》题（甘肃省级卷）.pdf": "gwy_gansu_2020_ShenJi",
            "2021年公务员多省联考《申论》题（甘肃乡镇卷）.pdf": "gwy_gansu_2021_XiangZhen",
            "2021年公务员多省联考《申论》题（甘肃省市县卷）.pdf": "gwy_gansu_2021_ShiXian",
            "2022年公务员多省联考《申论》题（甘肃县乡卷）.pdf": "gwy_gansu_2022_XianXiang",
            "2023年公务员多省联考《申论》题（甘肃县乡卷）.pdf": "gwy_gansu_2023_XianXiang",
            "2024年公务员多省联考《申论》题（甘肃县乡卷）.pdf": "gwy_gansu_2024_XianXiang",
        },
    ),
    "福建": (
        SHENLUN_BASE / "福建",
        "福建",
        {
            "2018年公务员多省联考《申论》题（福建乡镇卷）.pdf": "gwy_fujian_2018_XiangZhen",
            "2018年公务员多省联考《申论》题（福建县级卷）.pdf": "gwy_fujian_2018_XianJi",
            "2019年公务员多省联考《申论》题（福建乡镇卷）.pdf": "gwy_fujian_2019_XiangZhen",
            "2019年公务员多省联考《申论》题（福建县级卷）.pdf": "gwy_fujian_2019_XianJi",
            "2020年0725公务员多省联考《申论》题（福建乡镇卷）.pdf": "gwy_fujian_2020_XiangZhen",
            "2020年0725公务员多省联考《申论》题（福建县级卷）.pdf": "gwy_fujian_2020_XianJi",
            "2021年公务员多省联考《申论》题（福建乡镇卷）.pdf": "gwy_fujian_2021_XiangZhen",
            "2021年公务员多省联考《申论》题（福建县级卷）.pdf": "gwy_fujian_2021_XianJi",
            "2022年公务员多省联考《申论》题（福建县乡卷）.pdf": "gwy_fujian_2022_XianXiang",
            "2022年公务员多省联考《申论》题（福建省市卷）.pdf": "gwy_fujian_2022_ShiShi",
            "2022年公务员多省联考《申论》题（福建行政执法卷）.pdf": "gwy_fujian_2022_XingZhengZhiFa",
            "2023年公务员多省联考《申论》题（福建县乡卷）.pdf": "gwy_fujian_2023_XianXiang",
            "2023年公务员多省联考《申论》题（福建省市卷）.pdf": "gwy_fujian_2023_ShiShi",
            "2024年公务员多省联考《申论》题（福建县乡卷）.pdf": "gwy_fujian_2024_XianXiang",
            "2024年公务员多省联考《申论》题（福建省市卷）.pdf": "gwy_fujian_2024_ShiShi",
            "2024年公务员多省联考《申论》题（福建行政执法卷）.pdf": "gwy_fujian_2024_XingZhengZhiFa",
            "2025年公务员多省联考《申论》题（福建省市卷）.pdf": "gwy_fujian_2025_city",
            "2025年公务员多省联考《申论》题（福建通用卷）.pdf": "gwy_fujian_2025_TongYong",
        },
    ),
    "江苏": (
        SHENLUN_BASE,
        "江苏",
        {
            "2021年江苏省公考《申论》题（A、普通选调卷）.pdf": "gwy_jiangsu_2021_A",
            "2022年江苏省公考《申论》题（A、普通选调卷）.pdf": "gwy_jiangsu_2022_A",
            "2023年江苏省公考《申论》题（A、乡镇选调卷）.pdf": "gwy_jiangsu_2023_A",
            "2024年江苏省公考《申论》题（A、乡镇选调卷）.pdf": "gwy_jiangsu_2024_A",
            "2025年江苏省公考《申论》题（A、乡镇选调卷）.pdf": "gwy_jiangsu_2025_A",
            "2025年江苏省公考《申论》题（C卷）.pdf": "gwy_jiangsu_2025_C",
        },
    ),
    "广西": (
        SHENLUN_BASE / "广西",
        "广西",
        {
            "2018年广西公考《申论》题（A、普通选调卷）.pdf": "gwy_guangxi_2018_A",
            "2018年广西公考《申论》题（B卷）.pdf": "gwy_guangxi_2018_B",
            "2019年公务员多省联考《申论》题（广西A、普通选调卷）.pdf": "gwy_guangxi_2019_A",
            "2019年公务员多省联考《申论》题（广西B卷）.pdf": "gwy_guangxi_2019_B",
            "2020年0822公务员多省联考《申论》题（广西A卷）.pdf": "gwy_guangxi_2020_A",
            "2020年0822公务员多省联考《申论》题（广西B、普通选调卷）.pdf": "gwy_guangxi_2020_B",
            "2020年0822公务员多省联考《申论》题（广西C卷）.pdf": "gwy_guangxi_2020_C",
            "2021年公务员多省联考《申论》题（广西A、普通选调卷）.pdf": "gwy_guangxi_2021_A",
            "2021年公务员多省联考《申论》题（广西B卷）.pdf": "gwy_guangxi_2021_B",
            "2021年公务员多省联考《申论》题（广西C卷）.pdf": "gwy_guangxi_2021_C",
            "2022年公务员多省联考《申论》题（广西A、普通选调卷）.pdf": "gwy_guangxi_2022_A",
            "2023年公务员多省联考《申论》题（广西A、普通选调卷）.pdf": "gwy_guangxi_2023_A",
            "2023年公务员多省联考《申论》题（广西B卷）.pdf": "gwy_guangxi_2023_B",
            "2023年公务员多省联考《申论》题（广西C卷）.pdf": "gwy_guangxi_2023_C",
            "2024年公务员多省联考《申论》题（广西A、普通选调卷）.pdf": "gwy_guangxi_2024_A",
            "2024年公务员多省联考《申论》题（广西C卷）.pdf": "gwy_guangxi_2024_C",
            "2025年公务员多省联考《申论》题（广西B卷）.pdf": "gwy_guangxi_2025_B",
        },
    ),
    "贵州": (
        SHENLUN_BASE / "贵州",
        "贵州",
        {
            "2018年公务员多省联考《申论》题（贵州A、普通选调卷）.pdf": "gwy_guizhou_2018_A",
            "2018年公务员多省联考《申论》题（贵州B卷）.pdf": "gwy_guizhou_2018_B",
            "2019年公务员多省联考《申论》题（贵州A、普通选调卷）.pdf": "gwy_guizhou_2019_A",
            "2019年公务员多省联考《申论》题（贵州B卷）.pdf": "gwy_guizhou_2019_B",
            "2020年0822公务员多省联考《申论》题（贵州A卷）.pdf": "gwy_guizhou_2020_A",
            "2020年0822公务员多省联考《申论》题（贵州B卷）.pdf": "gwy_guizhou_2020_B",
            "2020年0822公务员多省联考《申论》题（贵州C卷）.pdf": "gwy_guizhou_2020_C",
            "2021年公务员多省联考《申论》题（贵州A卷）.pdf": "gwy_guizhou_2021_A",
            "2021年公务员多省联考《申论》题（贵州B卷）.pdf": "gwy_guizhou_2021_B",
            "2022年公务员多省联考《申论》题（贵州B卷）.pdf": "gwy_guizhou_2022_B",
            "2023年公务员多省联考《申论》题（贵州A卷）.pdf": "gwy_guizhou_2023_A",
            "2023年公务员多省联考《申论》题（贵州B卷）.pdf": "gwy_guizhou_2023_B",
            "2024年公务员多省联考《申论》题（贵州A卷）.pdf": "gwy_guizhou_2024_A",
            "2024年公务员多省联考《申论》题（贵州B卷）.pdf": "gwy_guizhou_2024_B",
            "2025年公务员多省联考《申论》题（贵州B卷）.pdf": "gwy_guizhou_2025_B",
        },
    ),
    "河北": (
        SHENLUN_BASE / "河北",
        "河北",
        {
            "2018年公务员多省联考《申论》题（河北、普通选调卷）.pdf": "gwy_hebei_2018",
            "2019年河北省公考《申论》题（乡镇卷）.pdf": "gwy_hebei_2019_XiangZhen",
            "2019年河北省公考《申论》题（县级卷）.pdf": "gwy_hebei_2019_XianJi",
            "2020年0822公务员多省联考《申论》题（河北乡镇、普通选调卷）.pdf": "gwy_hebei_2020_XiangZhen",
            "2020年0822公务员多省联考《申论》题（河北县级卷）.pdf": "gwy_hebei_2020_XianJi",
            "2021年公务员多省联考《申论》题（河北乡镇卷）.pdf": "gwy_hebei_2021_XiangZhen",
            "2021年公务员多省联考《申论》题（河北县级卷）.pdf": "gwy_hebei_2021_XianJi",
            "2022年公务员多省联考《申论》题（河北A卷）.pdf": "gwy_hebei_2022_A",
            "2022年公务员多省联考《申论》题（河北C卷）.pdf": "gwy_hebei_2022_C",
            "2023年公务员多省联考《申论》题（河北A卷）.pdf": "gwy_hebei_2023_A",
            "2023年公务员多省联考《申论》题（河北B卷）.pdf": "gwy_hebei_2023_B",
            "2023年公务员多省联考《申论》题（河北C卷）.pdf": "gwy_hebei_2023_C",
            "2024年公务员多省联考《申论》题（河北A卷）.pdf": "gwy_hebei_2024_A",
            "2024年公务员多省联考《申论》题（河北B、普通选调卷）.pdf": "gwy_hebei_2024_B",
            "2024年公务员多省联考《申论》题（河北C卷）.pdf": "gwy_hebei_2024_C",
            "2025年公务员多省联考《申论》题（河北A卷）.pdf": "gwy_hebei_2025_A",
            "2025年公务员多省联考《申论》题（河北B卷）（网友回忆版）.pdf": "gwy_hebei_2025_B",
            "2025年公务员多省联考《申论》题（河北C卷）（网友回忆版）.pdf": "gwy_hebei_2025_C",
        },
    ),
    "广东": (
        SHENLUN_BASE / "广东",
        "广东",
        {
            "2018年广东省公考《申论》题.pdf": "gwy_guangdong_2018",
            "2019年广东省公考《申论》题（乡镇）.pdf": "gwy_guangdong_2019_XiangZhen",
            "2019年广东省公考《申论》题（县级）.pdf": "gwy_guangdong_2019_XianJi",
            "2020年广东省公考《申论》题（乡镇）.pdf": "gwy_guangdong_2020_XiangZhen",
            "2020年广东省公考《申论》题（县级）.pdf": "gwy_guangdong_2020_XianJi",
            "2021年广东省公考《申论》题（乡镇）.pdf": "gwy_guangdong_2021_XiangZhen",
            "2021年广东省公考《申论》题（县级）.pdf": "gwy_guangdong_2021_XianJi",
            "2022年广东省公考《申论》题（乡镇）.pdf": "gwy_guangdong_2022_XiangZhen",
            "2022年广东省公考《申论》题（县级）.pdf": "gwy_guangdong_2022_XianJi",
            "2023年广东省公考《申论》题（乡镇）.pdf": "gwy_guangdong_2023_XiangZhen",
            "2023年广东省公考《申论》题（县级）.pdf": "gwy_guangdong_2023_XianJi",
            "2024年广东省公考《申论》题（公安）.pdf": "gwy_guangdong_2024_GongAn",
            "2024年广东省公考《申论》题（县镇）.pdf": "gwy_guangdong_2024_XianZhen",
            "2024年广东省公考《申论》题（省市）.pdf": "gwy_guangdong_2024_ShiShi",
            "2024年广东省公考《申论》题（行政执法）.pdf": "gwy_guangdong_2024_XingZhengZhiFa",
            "2025年广东省公考《申论》题（公安）.pdf": "gwy_guangdong_2025_GongAn",
            "2025年广东省公考《申论》题（县镇）.pdf": "gwy_guangdong_2025_XianZhen",
            "2025年广东省公考《申论》题（省市）.pdf": "gwy_guangdong_2025_ShiShi",
            "2025年广东省公考《申论》题（行政执法）.pdf": "gwy_guangdong_2025_XingZhengZhiFa",
            "2026年广东省公考《申论》题（公安）.pdf": "gwy_guangdong_2026_GongAn",
            "2026年广东省公考《申论》题（县镇）.pdf": "gwy_guangdong_2026_XianZhen",
            "2026年广东省公考《申论》题（省市）（网友回忆版）.pdf": "gwy_guangdong_2026_ShiShi",
            "2026年广东省公考《申论》题（行政执法）（网友回忆版）.pdf": "gwy_guangdong_2026_XingZhengZhiFa",
        },
    ),
}


def get_underlined_spans(page) -> list:
    # 1. Find horizontal lines
    lines = page.lines
    rects = page.rects
    horizontal_lines = []
    for line in lines:
        if line['width'] > 5 and line['height'] < 2:
            horizontal_lines.append(line)
    for rect in rects:
        if rect['width'] > 5 and rect['height'] < 2:
            horizontal_lines.append(rect)
    
    if not horizontal_lines:
        return []

    # 2. Find overlapping words
    words = page.extract_words(keep_blank_chars=True, x_tolerance=2, y_tolerance=2)
    underlined_words = []
    
    for word in words:
        is_underlined = False
        for line in horizontal_lines:
            v_dist = line['top'] - word['bottom']
            h_overlap = max(0, min(word['x1'], line['x1']) - max(word['x0'], line['x0']))
            if -2 < v_dist < 5 and h_overlap > (word['x1'] - word['x0']) * 0.5:
                is_underlined = True
                break
        if is_underlined:
            underlined_words.append(word)
            
    if not underlined_words:
        return []

    # 3. Group words into spans
    # Sort by vertical position then horizontal
    underlined_words.sort(key=lambda w: (round(w['top'], 1), w['x0']))
    
    spans = []
    current_span = []
    
    for i, word in enumerate(underlined_words):
        if not current_span:
            current_span.append(word)
            continue
        
        last_word = current_span[-1]
        # Check if same line (similar top) and close horizontally
        if abs(word['top'] - last_word['top']) < 5 and (word['x0'] - last_word['x1']) < 10:
            current_span.append(word)
        else:
            # End of span
            text = "".join([w['text'] for w in current_span])
            spans.append(text)
            current_span = [word]
            
    if current_span:
        text = "".join([w['text'] for w in current_span])
        spans.append(text)
        
    return spans


def extract_full_text(pdf_path: Path) -> str:
    full = []
    with pdfplumber.open(pdf_path) as pdf:
        for p in pdf.pages:
            t = p.extract_text()
            if t:
                spans = get_underlined_spans(p)
                for span in spans:
                    if span in t:
                        t = t.replace(span, f"<u>{span}</u>")
                full.append(t)
    raw = "\n".join(full)
    return unicodedata.normalize("NFKC", raw)


def _clean_footer(text: str) -> str:
    text = re.sub(r"·\s*本试卷由[^\n]+?第\s*\d+\s*页[，,\s]*共\s*\d+\s*页[^\n]*", "", text)
    # Safer header removal (multiline, anchored to start of line)
    text = re.sub(r"(?m)^\s*\d{4}年.+?《申论》题.*$", "", text)
    return text


def _find_zuoda_pos(text: str) -> int:
    for m in re.finditer(r"作答要求\s*\n\s*第[一二三四五六七八九十]+题", text):
        return m.start()
    last = -1
    for m in re.finditer(r"作答要求", text):
        last = m.start()
    return last


def parse_materials_liankao(text: str) -> list:
    """多省联考格式：材料1/给定资料1 分割"""
    first_q = re.search(r"第[一二三四五六七八九十]+题", text)
    req_pos = _find_zuoda_pos(text)
    if req_pos < 0 and first_q:
        req_pos = first_q.start()
    elif req_pos < 0:
        req_pos = len(text)

    start_markers = [
        r"给定材料\s*\n\s*材料1",
        r"给定材料\s*\n\s*给定资料1",
        r"\n\s*材料1\s*\n",
        r"\n\s*给定资料1\s*\n",
        r"材料1\s",
    ]
    materials_start = 0
    for pat in start_markers:
        m = re.search(pat, text)
        if m:
            materials_start = m.start()
            break
    materials_text = text[materials_start:req_pos] if req_pos > 0 else text[materials_start:]

    parts = re.split(r"\n\s*(材料|给定资料)(\d+)\s*\n", materials_text, flags=re.IGNORECASE)
    materials = []
    for i in range(1, len(parts) - 1, 3):
        if i + 2 <= len(parts):
            num = parts[i + 1]
            content = parts[i + 2].strip()
            content = _clean_footer(content)
            content = re.sub(r"[ \t]+", " ", content)
            content = re.sub(r"\n{3,}", "\n\n", content).strip()
            if len(content) > 30:
                materials.append({"id": f"m{num}", "title": f"材料{num}", "content": content})
    return materials


def parse_questions_liankao(text: str, material_ids: list) -> list:
    """多省联考格式：第X题 分割，解析分值、字数"""
    req_pos = _find_zuoda_pos(text)
    if req_pos < 0:
        req_pos = text.find("第一题") if "第一题" in text else 0
    q_text = text[req_pos:]
    if "答题纸" in q_text:
        q_text = q_text[: q_text.find("答题纸")]

    q_blocks = re.split(r"\n\s*第([一二三四五六七八九十]+)题\s*\n", q_text)
    questions = []
    for i in range(1, len(q_blocks), 2):
        if i + 1 > len(q_blocks):
            break
        block = q_blocks[i + 1].strip()
        
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        title_part, req_part = "", ""
        max_score, word_limit = 20, 300
        
        title_lines = []
        req_found = False
        
        for j, line in enumerate(lines):
            sm = re.search(r"[（(]本题\s*(\d+)\s*分[)）]", line)
            if sm:
                max_score = int(sm.group(1))
            elif re.search(r"[（(](\d+)\s*分[）)]", line):
                max_score = int(re.search(r"[（(](\d+)\s*分[）)]", line).group(1))
            
            w1 = re.search(r"不超过\s*(\d+)\s*字", line)
            w2 = re.search(r"(?:篇幅|字数)\s*(?:在|为)?\s*(\d+)\s*[—\-~～]\s*(\d+)\s*字", line)
            w4 = re.search(r"不少于\s*(\d+)\s*字", line)
            if w1:
                word_limit = int(w1.group(1))
            elif w4:
                word_limit = int(w4.group(1))
            elif w2:
                word_limit = (int(w2.group(1)) + int(w2.group(2))) // 2
            
            if "要求" in line or "（1）" in line:
                req_found = True
                req_lines = []
                for k in range(j, len(lines)):
                    ln = lines[k].strip()
                    nq = re.search(r"第[一二三四五六七八九十]+题", ln)
                    if nq:
                        req_lines.append(ln[: nq.start()].strip())
                        break
                    req_lines.append(ln)
                req_part = " ".join(req_lines)
                break
            
            title_lines.append(line)
        
        if req_found:
            title_part = " ".join(title_lines)
        else:
            # Fallback to regex if keyword not found
            req_match = re.search(r"要求[：:]\s*(.+?)(?=第[一二三四五六七八九十]+题|$)", block, re.DOTALL)
            if req_match:
                req_part = req_match.group(1).strip()
                title_part = block.replace(req_match.group(0), "").strip()
            else:
                title_part = " ".join(lines)
        
        if not title_part:
            title_part = lines[0] if lines else block[:100]

        title_part = re.sub(r"\s+", " ", title_part).strip()
        req_part = re.sub(r"\s+", " ", _clean_footer(req_part)).strip()

        refs = re.findall(r'[「"]?给定资料(\d+)[」"]?|[「"]?材料(\d+)[」"]?', title_part)
        mat_refs = list({f"m{a or b}" for a, b in refs if (a or b) and f"m{a or b}" in material_ids})

        is_last = i + 2 >= len(q_blocks)
        is_essay = is_last or ("写一篇" in block and ("1000" in block or "800" in block))
        if is_essay:
            q_type, mat_refs = "ESSAY", material_ids
        else:
            q_type = "SMALL"
            if not mat_refs and material_ids:
                mat_refs = [material_ids[0]]
        
        # Recalculate word limit if not found inline
        if word_limit == 300:
             wm = re.search(r"不超过\s*(\d+)\s*字|不少于\s*(\d+)\s*字|(\d+)[～~\-—]\s*(\d+)\s*字", block)
             if wm:
                if wm.group(1):
                    word_limit = int(wm.group(1))
                elif wm.group(2):
                    word_limit = int(wm.group(2))
                elif wm.group(3) and wm.group(4):
                    word_limit = (int(wm.group(3)) + int(wm.group(4))) // 2

        questions.append({
            "id": f"q{len(questions)+1}",
            "title": title_part[:500],
            "requirements": req_part,
            "maxScore": max_score,
            "wordLimit": word_limit,
            "type": q_type,
            "materialIds": mat_refs,
        })
    return questions


def parse_materials_guangdong(text: str) -> list:
    """广东格式"""
    first_q = re.search(r"第[一二三四五六七八九十\d]+题", text)
    if first_q:
        before = text[: first_q.start()]
        last_zy = before.rfind("作答要求")
        if last_zy >= 0:
            text = text[:last_zy]
    text = re.sub(r"·\s*本试卷由[\s\S]*?共\s*\d+\s*页", "", text)
    # Remove headers safely (multiline mode)
    text = re.sub(r"(?m)^\s*\d{4}年.+?《申论》题.*$", "", text)

    pattern = re.compile(r"(?:材料|给定资料)(\d+)")
    parts = []
    last_end = 0
    for m in pattern.finditer(text):
        idx = int(m.group(1))
        if parts:
            prev = text[last_end : m.start()].strip()
            prev = re.sub(r"·\s*本试卷由[\s\S]*?共\s*\d+\s*页", "", prev).strip()
            parts[-1]["content"] = prev
        parts.append({"id": idx, "title": m.group(0), "content": ""})
        last_end = m.end()
    if parts:
        prev = text[last_end:].strip()
        prev = re.sub(r"·\s*本试卷由[\s\S]*?共\s*\d+\s*页", "", prev).strip()
        parts[-1]["content"] = prev

    materials = []
    for p in parts:
        if not p["content"].strip():
            continue
        content = re.sub(r"\s+", " ", p["content"])
        # content = re.sub(r"\d{4}年[^题]+《申论》题", "", content) # Removed dangerous regex
        materials.append({"id": f"m{p['id']}", "title": p["title"], "content": content})
    return materials


def parse_questions_guangdong(text: str, materials: list) -> list:
    """广东格式"""
    first_q = re.search(r"第[一二三四五六七八九十\d]+题", text)
    if not first_q:
        return []
    before = text[: first_q.start()]
    last_zy = before.rfind("作答要求")
    if last_zy < 0:
        return []
    q_block = text[last_zy:]
    q_block = re.sub(r"^作答要求\s*", "", q_block, count=1)
    q_block = re.sub(r"·\s*本试卷由[\s\S]*?共\s*\d+\s*页", "", q_block)
    q_block = re.sub(r"答题纸[\s\S]*", "", q_block)

    q_pattern = re.compile(r"第[一二三四五六七八九十\d]+题\s*")
    raw_parts = [p.strip() for p in q_pattern.split(q_block) if p.strip()]

    material_ids = [m["id"] for m in materials]
    questions = []
    for i, block in enumerate(raw_parts):
        if len(block) < 5:
            continue
        if any(k in block for k in ("准考证", "答题卡", "考试时限", "超出答题区域")) and not any(
            k in block for k in ("根据", "概括", "材料", "给定资料", "写一")
        ):
            continue

        lines = [l.strip() for l in block.split("\n") if l.strip()]
        title, requirements, max_score, word_limit = "", "", None, None

        title_lines = []
        req_found = False
        
        for j, line in enumerate(lines):
            sm = re.search(r"[（(]本题\s*(\d+)\s*分[)）]", line)
            if sm and max_score is None:
                max_score = int(sm.group(1))
            w1 = re.search(r"不超过\s*(\d+)\s*字", line)
            w2 = re.search(r"(?:篇幅|字数)\s*(?:在|为)?\s*(\d+)\s*[—\-~～]\s*(\d+)\s*字", line)
            w4 = re.search(r"不少于\s*(\d+)\s*字", line)
            if w1 and word_limit is None:
                word_limit = int(w1.group(1))
            elif w4 and word_limit is None:
                word_limit = int(w4.group(1))
            elif w2 and word_limit is None:
                word_limit = (int(w2.group(1)) + int(w2.group(2))) // 2

            if "要求" in line or "（1）" in line:
                req_found = True
                req_lines = []
                for k in range(j, len(lines)):
                    ln = lines[k].strip()
                    nq = re.search(r"第[一二三四五六七八九十\d]+题", ln)
                    if nq:
                        req_lines.append(ln[: nq.start()].strip())
                        break
                    req_lines.append(ln)
                requirements = " ".join(req_lines)
                break
            
            title_lines.append(line)

        if req_found:
            title = " ".join(title_lines)
        else:
            # Try to find requirements with regex if not found by keyword
            rm = re.search(r"要求[：:]\s*([\s\S]*?)(?=第[一二三四五六七八九十\d]+题|$)", block)
            if rm:
                requirements = rm.group(1).strip()
                title = block.replace(rm.group(0), "").strip()
            else:
                title = " ".join(lines)

        if not title:
            title = lines[0] if lines else block[:100]
        if not requirements:
            rm = re.search(r"要求[：:]\s*([\s\S]*?)(?=第[一二三四五六七八九十\d]+题|$)", block)
            requirements = rm.group(1).strip() if rm else ""

        requirements = re.sub(r"\d{4}年[^题]+《申论》题", "", requirements).strip()

        block_t = title + " " + block
        is_essay = (
            ("写一篇文章" in block_t or "议论文" in block_t or ("写一篇" in block_t and "文章" in block_t))
            or ("自选" in block_t and "角度" in block_t and ("拟题" in block_t or "写一篇" in block_t))
        ) and "短评" not in block_t
        is_essay = is_essay or bool(re.search(r"不少于\s*(?:[89]\d{2}|1\d{3,})\s*字", block_t))

        mat_refs = material_ids if is_essay else _infer_mats(block_t, material_ids)
        if not mat_refs:
            mat_refs = material_ids

        q_type = "ESSAY" if is_essay else "SMALL"
        max_score = max_score or 20
        if word_limit is None:
            w = re.search(r"(?:篇幅|字数)\s*(\d+)\s*[—\-~～]\s*(\d+)\s*字", block)
            w4 = re.search(r"不少于\s*(\d+)\s*字", block)
            word_limit = int(w4.group(1)) if w4 else ((int(w.group(1)) + int(w.group(2))) // 2 if w else (900 if is_essay else 300))

        questions.append({
            "id": f"q{i+1}",
            "title": title.strip(),
            "requirements": requirements or "无",
            "maxScore": max_score,
            "wordLimit": word_limit,
            "type": q_type,
            "materialIds": mat_refs,
        })
    return questions


def _infer_mats(text: str, material_ids: list) -> list:
    if any(kw in text for kw in ["全部给定材料", "所有给定材料"]):
        return material_ids
    m2 = re.search(r"(?:材料|给定资料)([\d、,，\s]+)", text)
    if m2:
        nums = [int(x) for x in re.findall(r"\d+", m2.group(1))]
        if nums:
            return [f"m{n}" for n in range(min(nums), max(nums) + 1) if f"m{n}" in material_ids]
    m1 = re.findall(r"(?:根据)?(?:材料|给定资料)(\d+)", text)
    return list(dict.fromkeys([f"m{int(n)}" for n in m1 if f"m{int(n)}" in material_ids]))


def process_liankao(pdf_path: Path, region: str, paper_id: str, name: str, year: int) -> dict | None:
    text = extract_full_text(pdf_path)
    if not text or len(text) < 500:
        return None
    materials = parse_materials_liankao(text)
    if not materials:
        return None
    material_ids = [m["id"] for m in materials]
    questions = parse_questions_liankao(text, material_ids)
    if not questions:
        return None
    return {
        "id": paper_id,
        "name": name,
        "examType": "公务员",
        "region": region,
        "year": year,
        "materials": materials,
        "questions": questions,
    }


def process_guangdong(pdf_path: Path, paper_id: str, name: str, year: int) -> dict | None:
    text = extract_full_text(pdf_path)
    if not text or len(text) < 500:
        return None
    materials = parse_materials_guangdong(text)
    if not materials:
        return None
    questions = parse_questions_guangdong(text, materials)
    if not questions:
        return None
    return {
        "id": paper_id,
        "name": name,
        "examType": "公务员",
        "region": "广东",
        "year": year,
        "materials": materials,
        "questions": questions,
    }


def main():
    regions_to_run = sys.argv[1:] if len(sys.argv) > 1 else list(REGIONS.keys())
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    success, fail = 0, 0

    for region_name in regions_to_run:
        if region_name not in REGIONS:
            print(f"未知区域: {region_name}")
            continue
        pdf_dir, region, mapping = REGIONS[region_name]
        if not pdf_dir.exists():
            print(f"[跳过] PDF 目录不存在: {pdf_dir}")
            continue

        print(f"\n===== {region_name} =====")
        for pdf_name, paper_id in mapping.items():
            pdf_path = pdf_dir / pdf_name
            if not pdf_path.exists():
                print(f"  [跳过-不存在] {pdf_name}")
                fail += 1
                continue

            year_m = re.search(r"(\d{4})", pdf_name)
            year = int(year_m.group(1)) if year_m else 2020
            name = pdf_name.replace(".pdf", "")

            try:
                if region_name == "广东":
                    data = process_guangdong(pdf_path, paper_id, name, year)
                else:
                    data = process_liankao(pdf_path, region, paper_id, name, year)

                if data and (data.get("materials") or data.get("questions")):
                    out_path = OUTPUT_DIR / f"{paper_id}.json"
                    with open(out_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    print(f"  ✓ {pdf_name} -> {paper_id}.json (材料{len(data['materials'])}则, 题目{len(data['questions'])}道)")
                    success += 1
                else:
                    print(f"  ✗ {pdf_name} 解析结果为空")
                    fail += 1
            except Exception as e:
                print(f"  ✗ {pdf_name} 失败: {e}")
                fail += 1

    print(f"\n===== 完成: 成功 {success}, 失败 {fail} =====")

    # 运行 fix_essay_fields 和 fix_scores
    scripts_dir = BASE / "scripts"
    for script in ["fix_essay_fields.py", "fix_scores.py"]:
        p = scripts_dir / script
        if p.exists():
            print(f"\n运行 {script} ...")
            subprocess.run([sys.executable, str(p)], cwd=str(BASE), check=False)


if __name__ == "__main__":
    main()
