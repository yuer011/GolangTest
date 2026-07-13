# !/usr/bin/env python3
import psutil
import time
import platform
import os
import subprocess
from datetime import datetime
from pyecharts.charts import Line, Bar
from pyecharts import options as opts
from pyecharts.globals import ThemeType

# 配置参数
DEFAULT_MONITOR_DURATION = 10  # 默认监控时长（秒）
DEFAULT_SAMPLE_INTERVAL = 1  # 默认采样间隔（秒）
TARGET_PROCESS_NAME = "corplink"  # 目标进程名称


def get_windows_target_directories():
    """
    获取Windows系统的目标监控目录
    """
    directories = []
    try:
        import getpass
        username = getpass.getuser()
        appdata_local = os.path.expandvars("%LOCALAPPDATA%")
        if not appdata_local or appdata_local == "%LOCALAPPDATA%":
            appdata_local = f"C:\\Users\\{username}\\AppData\\Local"

        directories.append(os.path.join(appdata_local, "corplink-ow", "db"))
        directories.append(os.path.join(appdata_local, "corplink-ow", "logs"))

        temp_dir = os.path.expandvars("%TEMP%")
        if temp_dir and temp_dir != "%TEMP%":
            directories.append(temp_dir)
    except Exception as e:
        print(f"获取Windows目标目录时出错: {e}")
    return directories


def get_mac_target_directories():
    """
    获取macOS系统的目标监控目录
    """
    directories = []
    directories.append("/Library/CorpLink/db")
    directories.append("/Library/CorpLink/logs")
    return directories


CURRENT_OS = platform.system()
if CURRENT_OS == "Darwin":
    TARGET_DIRECTORIES = get_mac_target_directories()
elif CURRENT_OS == "Windows":
    TARGET_DIRECTORIES = get_windows_target_directories()
else:
    TARGET_DIRECTORIES = []


def get_disk_partitions():
    """
    获取磁盘分区信息
    """
    partitions = psutil.disk_partitions()
    return partitions


def get_directory_size(path):
    """
    获取目录大小
    :param path: 目录路径
    :return: 目录大小（字节）
    """
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                except:
                    pass
    except:
        pass
    return total_size


def monitor_disk_io(duration, interval):
    """
    监控磁盘IO数据
    :param duration: 监控持续时间（秒）
    :param interval: 采样间隔（秒）
    :return: 时间戳列表，读取字节数列表，写入字节数列表，读取速度列表，写入速度列表
    """
    timestamps = []
    read_bytes = []
    write_bytes = []
    read_speed = []
    write_speed = []

    # 获取初始磁盘IO数据
    io_counters_start = psutil.disk_io_counters()
    initial_read = io_counters_start.read_bytes
    initial_write = io_counters_start.write_bytes

    # 上一次的IO数据
    last_read = initial_read
    last_write = initial_write

    start_time = time.time()
    current_time = start_time

    try:
        while current_time - start_time < duration:
            # 等待指定的采样间隔
            time.sleep(interval)
            current_time = time.time()

            # 获取当前磁盘IO数据
            io_counters = psutil.disk_io_counters()
            current_read = io_counters.read_bytes - initial_read
            current_write = io_counters.write_bytes - initial_write

            # 计算读写速度（字节/秒）
            current_speed_read = (io_counters.read_bytes - last_read) / interval
            current_speed_write = (io_counters.write_bytes - last_write) / interval

            # 更新上一次的IO数据
            last_read = io_counters.read_bytes
            last_write = io_counters.write_bytes

            # 记录时间戳和IO数据
            timestamps.append(datetime.fromtimestamp(current_time).strftime('%H:%M:%S'))
            read_bytes.append(current_read)
            write_bytes.append(current_write)
            read_speed.append(current_speed_read)
            write_speed.append(current_speed_write)
    except KeyboardInterrupt:
        print("\n检测到中断信号，正在生成图表...")

    return timestamps, read_bytes, write_bytes, read_speed, write_speed


def monitor_process_io(process_name, duration, interval):
    """
    监控指定进程的IO数据
    :param process_name: 进程名称
    :param duration: 监控持续时间（秒）
    :param interval: 采样间隔（秒）
    :return: 时间戳列表，读取字节数列表，写入字节数列表
    """
    timestamps = []
    read_bytes = []
    write_bytes = []

    start_time = time.time()
    current_time = start_time

    try:
        while current_time - start_time < duration:
            # 等待指定的采样间隔
            time.sleep(interval)
            current_time = time.time()

            # 查找包含指定名称的进程
            process_io_read = 0
            process_io_write = 0

            for proc in psutil.process_iter(['name']):
                try:
                    if process_name.lower() in proc.info['name'].lower():
                        # 获取进程的IO计数器
                        io_counters = proc.io_counters()
                        process_io_read += io_counters.read_bytes
                        process_io_write += io_counters.write_bytes
                except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                    pass

            # 记录时间戳和IO数据
            timestamps.append(datetime.fromtimestamp(current_time).strftime('%H:%M:%S'))
            read_bytes.append(process_io_read)
            write_bytes.append(process_io_write)
    except KeyboardInterrupt:
        pass

    return timestamps, read_bytes, write_bytes


def get_mac_oslog_size():
    """
    获取macOS系统日志中corplink相关日志的大小估算
    :return: oslog日志大小估算（字节）
    """
    total_size = 0
    try:
        result = subprocess.run(
            ['log', 'show', '--predicate', 'subsystem CONTAINS "com.volcengine.corplink"', '--last', '1h', '--info'],
            capture_output=True, text=True
        )
        log_content = result.stdout
        if log_content:
            total_size = len(log_content.encode('utf-8'))

        result2 = subprocess.run(
            ['log', 'show', '--predicate', 'sender CONTAINS "corplink"', '--last', '1h', '--info'],
            capture_output=True, text=True
        )
        log_content2 = result2.stdout
        if log_content2:
            total_size += len(log_content2.encode('utf-8'))

        print(f"oslog日志估算大小: {total_size} 字节")
    except Exception as e:
        print(f"获取oslog日志大小失败: {e}")
    return total_size


def get_mac_disk_usage():
    """
    获取Mac系统的磁盘占用信息（使用diskutil命令）
    :return: 已使用空间（GB），未使用空间（GB）
    """
    print("=== 获取Mac磁盘占用信息 ===")
    try:
        # 使用diskutil命令获取APFS容器信息
        result = subprocess.run(['diskutil', 'apfs', 'list'], capture_output=True, text=True)
        print("diskutil apfs list 输出:")
        print(result.stdout)

        # 解析输出获取总容量、已使用和可用空间
        total_bytes = 0
        used_bytes = 0
        free_bytes = 0

        # 查找APFS容器
        for line in result.stdout.splitlines():
            line = line.strip()
            if 'Size (Capacity Ceiling):' in line:
                # 提取总容量
                parts = line.split('Size (Capacity Ceiling):')[-1].strip().split()
                if len(parts) >= 3:
                    size_str = parts[0]
                    total_bytes = float(size_str)
                    print(f"总容量: {total_bytes} B")
            elif 'Capacity In Use By Volumes:' in line:
                # 提取已使用空间
                parts = line.split('Capacity In Use By Volumes:')[-1].strip().split()
                if len(parts) >= 3:
                    size_str = parts[0]
                    used_bytes = float(size_str)
                    print(f"已使用: {used_bytes} B")
            elif 'Capacity Not Allocated:' in line:
                # 提取可用空间
                parts = line.split('Capacity Not Allocated:')[-1].strip().split()
                if len(parts) >= 3:
                    size_str = parts[0]
                    free_bytes = float(size_str)
                    print(f"可用: {free_bytes} B")

        if total_bytes > 0 and used_bytes > 0 and free_bytes > 0:
            # 转换为GB并保留两位小数
            used_gb = round(used_bytes / (1000 ** 3), 2)
            free_gb = round(free_bytes / (1000 ** 3), 2)
            print(
                f"APFS容器计算结果 - 已使用: {used_gb} GB, 未使用: {free_gb} GB, 总容量: {round(total_bytes / (1000 ** 3), 2)} GB")
            return used_gb, free_gb
    except Exception as e:
        print(f"使用diskutil获取APFS信息时出错: {e}")

    # 如果diskutil命令失败，尝试使用df命令计算所有分区的总和
    print("尝试使用df命令获取磁盘信息")
    try:
        # 使用df命令获取磁盘信息
        result = subprocess.run(['df', '-H'], capture_output=True, text=True)
        print("df -H 输出:")
        print(result.stdout)

        # 计算所有APFS分区的总使用量和总可用量
        total_used = 0
        total_free = 0
        total_capacity = 0

        for line in result.stdout.splitlines():
            # 查找APFS分区
            if 'devfs' in line or 'map' in line or 'AppTranslocation' in line:
                continue
            if '/dev/disk' in line and ('/' in line or 'Data' in line):
                print(f"处理分区: {line}")
                parts = line.split()
                if len(parts) >= 4:
                    try:
                        # 提取使用量和可用量
                        size_str = parts[1]
                        used_str = parts[2]
                        avail_str = parts[3]

                        # 转换为GB
                        def convert_to_gb(size_str):
                            if 'G' in size_str:
                                return float(size_str.replace('G', ''))
                            elif 'T' in size_str:
                                return float(size_str.replace('T', '')) * 1000
                            elif 'M' in size_str:
                                return float(size_str.replace('M', '')) / 1000
                            else:
                                return 0

                        capacity = convert_to_gb(size_str)
                        used = convert_to_gb(used_str)
                        avail = convert_to_gb(avail_str)

                        # 只统计主要分区（容量大于100GB）
                        if capacity > 100:
                            total_used += used
                            total_free = avail  # 使用最大的可用空间值
                            total_capacity = capacity
                            print(f"  分区容量: {capacity} GB, 已使用: {used} GB, 可用: {avail} GB")
                    except Exception as e:
                        print(f"解析df输出时出错: {e}")
                        pass

        if total_capacity > 0:
            print(f"df计算结果 - 已使用: {total_used} GB, 未使用: {total_free} GB, 总容量: {total_capacity} GB")
            return round(total_used, 2), round(total_free, 2)
    except Exception as e:
        print(f"使用df获取磁盘信息时出错: {e}")

    # 如果所有命令都失败，回退到psutil
    print("回退到psutil获取磁盘信息")
    try:
        # 获取根目录
        usage = psutil.disk_usage('/')

        # 使用1000^3计算GB，与系统设置一致
        used_gb = round(usage.used / (1000 ** 3), 2)
        free_gb = round(usage.free / (1000 ** 3), 2)
        total_gb = round(usage.total / (1000 ** 3), 2)
        print(f"psutil计算结果 - 已使用: {used_gb} GB, 未使用: {free_gb} GB, 总容量: {total_gb} GB")
        return used_gb, free_gb
    except Exception as e:
        print(f"psutil获取磁盘信息时出错: {e}")
        pass

    print("所有方法都失败，返回0")
    return 0, 0


def monitor_disk_usage(duration, interval):
    """
    监控磁盘占用情况
    :param duration: 监控持续时间（秒）
    :param interval: 采样间隔（秒）
    :return: 时间戳列表，磁盘占用数据字典
    """
    timestamps = []
    disk_usage_data = {}

    # 初始化总磁盘占用数据
    disk_usage_data["总磁盘已使用(GB)"] = []
    disk_usage_data["总磁盘未使用(GB)"] = []

    # Windows系统额外统计每个盘的占用
    if CURRENT_OS == "Windows":
        partitions = get_disk_partitions()
        for partition in partitions:
            try:
                disk_usage_data[f"{partition.mountpoint} 已使用(GB)"] = []
                disk_usage_data[f"{partition.mountpoint} 未使用(GB)"] = []
            except:
                pass

    start_time = time.time()
    current_time = start_time

    try:
        while current_time - start_time < duration:
            # 等待指定的采样间隔
            time.sleep(interval)
            current_time = time.time()

            # 记录时间戳
            timestamps.append(datetime.fromtimestamp(current_time).strftime('%H:%M:%S'))

            # 计算总磁盘占用
            total_used = 0
            total_free = 0
            if CURRENT_OS == "Windows":
                # Windows系统计算总磁盘占用
                partitions = get_disk_partitions()
                for partition in partitions:
                    try:
                        usage = psutil.disk_usage(partition.mountpoint)
                        total_used += usage.used
                        total_free += usage.free
                        # 转换为GB并保留两位小数
                        used_gb = round(usage.used / (1024 ** 3), 2)
                        free_gb = round(usage.free / (1024 ** 3), 2)
                        disk_usage_data[f"{partition.mountpoint} 已使用(GB)"].append(used_gb)
                        disk_usage_data[f"{partition.mountpoint} 未使用(GB)"].append(free_gb)
                    except:
                        if f"{partition.mountpoint} 已使用(GB)" in disk_usage_data:
                            disk_usage_data[f"{partition.mountpoint} 已使用(GB)"].append(0)
                            disk_usage_data[f"{partition.mountpoint} 未使用(GB)"].append(0)
            else:
                # Mac系统计算总磁盘占用
                if CURRENT_OS == "Darwin":
                    # 使用专门的Mac磁盘占用获取函数
                    used_gb, free_gb = get_mac_disk_usage()
                    total_used = used_gb * (1000 ** 3)  # 转换回字节用于后续计算
                    total_free = free_gb * (1000 ** 3)
                    # 直接使用获取的值
                    disk_usage_data["总磁盘已使用(GB)"].append(used_gb)
                    disk_usage_data["总磁盘未使用(GB)"].append(free_gb)
                    print(f"添加到图表 - 已使用: {used_gb} GB, 未使用: {free_gb} GB")
                else:
                    # 其他系统
                    try:
                        usage = psutil.disk_usage('/')
                        total_used = usage.used
                        total_free = usage.free
                    except:
                        pass

            # 如果不是Mac系统，或者Mac系统获取失败，使用默认计算方式
            if CURRENT_OS != "Darwin" or not disk_usage_data["总磁盘已使用(GB)"]:
                # 转换为GB并保留两位小数
                # 使用与系统设置相同的计算方式（1000^3）
                total_used_gb = round(total_used / (1000 ** 3), 2)
                total_free_gb = round(total_free / (1000 ** 3), 2)
                disk_usage_data["总磁盘已使用(GB)"].append(total_used_gb)
                disk_usage_data["总磁盘未使用(GB)"].append(total_free_gb)
    except KeyboardInterrupt:
        pass

    return timestamps, disk_usage_data


def monitor_directory_usage(duration, interval, directories):
    """
    监控指定目录的占用情况
    :param duration: 监控持续时间（秒）
    :param interval: 采样间隔（秒）
    :param directories: 目录列表
    :return: 时间戳列表，目录占用数据字典
    """
    timestamps = []
    directory_usage_data = {}

    # 初始化目录占用数据字典
    for directory in directories:
        directory_usage_data[directory] = []

    start_time = time.time()
    current_time = start_time

    try:
        while current_time - start_time < duration:
            # 等待指定的采样间隔
            time.sleep(interval)
            current_time = time.time()

            # 记录时间戳
            timestamps.append(datetime.fromtimestamp(current_time).strftime('%H:%M:%S'))

            # 获取每个目录的大小
            for directory in directories:
                try:
                    size = get_directory_size(directory) / (1024 * 1024)  # 转换为MB
                    directory_usage_data[directory].append(round(size, 2))
                except:
                    directory_usage_data[directory].append(0)
    except KeyboardInterrupt:
        pass

    return timestamps, directory_usage_data


def generate_io_chart(timestamps, total_read, total_write, read_speed, write_speed, process_read, process_write):
    """
    生成IO曲线图
    """
    # 转换为MB并保留两位小数
    total_read_mb = [round(x / (1024 * 1024), 2) for x in total_read]
    total_write_mb = [round(x / (1024 * 1024), 2) for x in total_write]
    read_speed_mb = [round(x / (1024 * 1024), 2) for x in read_speed]  # 转换为MB/s
    write_speed_mb = [round(x / (1024 * 1024), 2) for x in write_speed]  # 转换为MB/s
    process_read_mb = [round(x / (1024 * 1024), 2) for x in process_read]
    process_write_mb = [round(x / (1024 * 1024), 2) for x in process_write]

    # 创建Line图表
    line = Line(init_opts=opts.InitOpts(theme=ThemeType.LIGHT, width="1000px", height="600px"))

    # 添加x轴数据（时间戳）
    line.add_xaxis(timestamps)

    # 添加y轴数据（读取和写入字节数）
    line.add_yaxis(
        "总读取(MB)",
        total_read_mb,
        is_smooth=True,
        itemstyle_opts=opts.ItemStyleOpts(color="#5470c6"),
        label_opts=opts.LabelOpts(is_show=False)
    )
    line.add_yaxis(
        "总写入(MB)",
        total_write_mb,
        is_smooth=True,
        itemstyle_opts=opts.ItemStyleOpts(color="#91cc75"),
        label_opts=opts.LabelOpts(is_show=False)
    )
    line.add_yaxis(
        "读取速度(MB/s)",
        read_speed_mb,
        is_smooth=True,
        itemstyle_opts=opts.ItemStyleOpts(color="#fac858"),
        label_opts=opts.LabelOpts(is_show=False)
    )
    line.add_yaxis(
        "写入速度(MB/s)",
        write_speed_mb,
        is_smooth=True,
        itemstyle_opts=opts.ItemStyleOpts(color="#ee6666"),
        label_opts=opts.LabelOpts(is_show=False)
    )
    line.add_yaxis(
        f"{TARGET_PROCESS_NAME}读取(MB)",
        process_read_mb,
        is_smooth=True,
        itemstyle_opts=opts.ItemStyleOpts(color="#73c0de"),
        label_opts=opts.LabelOpts(is_show=False)
    )
    line.add_yaxis(
        f"{TARGET_PROCESS_NAME}写入(MB)",
        process_write_mb,
        is_smooth=True,
        itemstyle_opts=opts.ItemStyleOpts(color="#3ba272"),
        label_opts=opts.LabelOpts(is_show=False)
    )

    # 设置图表标题和配置
    line.set_global_opts(
        title_opts=opts.TitleOpts(title="磁盘IO监控", pos_top="10"),
        tooltip_opts=opts.TooltipOpts(
            trigger="axis",
            axis_pointer_type="cross",
            formatter="{b}<br/>{a}: {c}"
        ),
        legend_opts=opts.LegendOpts(pos_top="40"),
        xaxis_opts=opts.AxisOpts(
            name="时间",
            axislabel_opts=opts.LabelOpts(rotate=45)
        ),
        yaxis_opts=opts.AxisOpts(
            name="值",
            axislabel_opts=opts.LabelOpts(formatter="{value}"),
            splitline_opts=opts.SplitLineOpts(is_show=True)
        ),
        toolbox_opts=opts.ToolboxOpts(
            feature={
                "saveAsImage": {},
                "dataZoom": {},
                "magicType": {"type": ["line", "bar"]}
            }
        )
    )

    # 保存图表为HTML文件
    output_file = f"disk_io_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    line.render(output_file)
    print(f"IO图表已保存为: {output_file}")


def generate_disk_usage_chart(timestamps, disk_usage_data):
    """
    生成磁盘占用曲线图
    """
    # 创建Line图表
    line = Line(init_opts=opts.InitOpts(theme=ThemeType.LIGHT, width="1000px", height="600px"))

    # 添加x轴数据（时间戳）
    line.add_xaxis(timestamps)

    # 添加磁盘占用数据
    for disk, usage in disk_usage_data.items():
        if usage:
            line.add_yaxis(
                disk,
                usage,
                is_smooth=True,
                itemstyle_opts=opts.ItemStyleOpts(),
                label_opts=opts.LabelOpts(is_show=False)
            )

    # 设置图表标题和配置
    line.set_global_opts(
        title_opts=opts.TitleOpts(title="磁盘占用监控", pos_top="10"),
        tooltip_opts=opts.TooltipOpts(
            trigger="axis",
            axis_pointer_type="cross",
            formatter="{b}<br/>{a}: {c} GB"
        ),
        legend_opts=opts.LegendOpts(pos_top="40"),
        xaxis_opts=opts.AxisOpts(
            name="时间",
            axislabel_opts=opts.LabelOpts(rotate=45)
        ),
        yaxis_opts=opts.AxisOpts(
            name="GB",
            axislabel_opts=opts.LabelOpts(formatter="{value} GB"),
            splitline_opts=opts.SplitLineOpts(is_show=True)
        ),
        toolbox_opts=opts.ToolboxOpts(
            feature={
                "saveAsImage": {},
                "dataZoom": {},
                "magicType": {"type": ["line", "bar"]}
            }
        )
    )

    # 保存图表为HTML文件
    output_file = f"disk_usage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    line.render(output_file)
    print(f"磁盘占用图表已保存为: {output_file}")


def generate_directory_usage_chart(timestamps, directory_usage_data):
    """
    生成目录占用曲线图
    """
    # 创建Line图表
    line = Line(init_opts=opts.InitOpts(theme=ThemeType.LIGHT, width="1000px", height="600px"))

    # 添加x轴数据（时间戳）
    line.add_xaxis(timestamps)

    # 添加每个目录的占用数据
    for directory, usage in directory_usage_data.items():
        if usage:
            line.add_yaxis(
                f"目录 {os.path.basename(directory)} 大小",
                usage,
                is_smooth=True,
                itemstyle_opts=opts.ItemStyleOpts(),
                label_opts=opts.LabelOpts(is_show=False)
            )

    # 设置图表标题和配置
    line.set_global_opts(
        title_opts=opts.TitleOpts(title="目录占用监控", pos_top="10"),
        tooltip_opts=opts.TooltipOpts(
            trigger="axis",
            axis_pointer_type="cross",
            formatter="{b}<br/>{a}: {c} MB"
        ),
        legend_opts=opts.LegendOpts(pos_top="40"),
        xaxis_opts=opts.AxisOpts(
            name="时间",
            axislabel_opts=opts.LabelOpts(rotate=45)
        ),
        yaxis_opts=opts.AxisOpts(
            name="MB",
            axislabel_opts=opts.LabelOpts(formatter="{value} MB"),
            splitline_opts=opts.SplitLineOpts(is_show=True)
        ),
        toolbox_opts=opts.ToolboxOpts(
            feature={
                "saveAsImage": {},
                "dataZoom": {},
                "magicType": {"type": ["line", "bar"]}
            }
        )
    )

    # 保存图表为HTML文件
    output_file = f"directory_usage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    line.render(output_file)
    print(f"目录占用图表已保存为: {output_file}")


def monitor_oslog(duration, interval):
    """
    监控macOS oslog日志大小变化
    :param duration: 监控持续时间（秒）
    :param interval: 采样间隔（秒）
    :return: 时间戳列表，oslog大小数据列表（MB）
    """
    timestamps = []
    oslog_sizes = []

    start_time = time.time()
    current_time = start_time

    try:
        while current_time - start_time < duration:
            time.sleep(interval)
            current_time = time.time()

            timestamps.append(datetime.fromtimestamp(current_time).strftime('%H:%M:%S'))
            size_bytes = get_mac_oslog_size()
            size_mb = round(size_bytes / (1024 * 1024), 2)
            oslog_sizes.append(size_mb)
    except KeyboardInterrupt:
        pass

    return timestamps, oslog_sizes


def generate_oslog_chart(timestamps, oslog_sizes):
    """
    生成oslog日志大小图表
    """
    line = Line(init_opts=opts.InitOpts(theme=ThemeType.LIGHT, width="1000px", height="600px"))

    line.add_xaxis(timestamps)
    line.add_yaxis(
        "oslog日志大小(MB)",
        oslog_sizes,
        is_smooth=True,
        itemstyle_opts=opts.ItemStyleOpts(color="#91cc75"),
        label_opts=opts.LabelOpts(is_show=False)
    )

    line.set_global_opts(
        title_opts=opts.TitleOpts(title="macOS oslog日志大小监控", pos_top="10"),
        tooltip_opts=opts.TooltipOpts(
            trigger="axis",
            axis_pointer_type="cross",
            formatter="{b}<br/>{a}: {c} MB"
        ),
        legend_opts=opts.LegendOpts(pos_top="40"),
        xaxis_opts=opts.AxisOpts(
            name="时间",
            axislabel_opts=opts.LabelOpts(rotate=45)
        ),
        yaxis_opts=opts.AxisOpts(
            name="MB",
            axislabel_opts=opts.LabelOpts(formatter="{value} MB"),
            splitline_opts=opts.SplitLineOpts(is_show=True)
        ),
        toolbox_opts=opts.ToolboxOpts(
            feature={
                "saveAsImage": {},
                "dataZoom": {},
                "magicType": {"type": ["line", "bar"]}
            }
        )
    )

    output_file = f"oslog_usage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    line.render(output_file)
    print(f"oslog图表已保存为: {output_file}")


def main():
    """
    主函数
    """
    print("开始监控磁盘IO和占用情况...")
    print("按Ctrl+C停止监控")
    print(f"当前操作系统: {CURRENT_OS}")
    print(f"监控目录: {TARGET_DIRECTORIES}")

    try:
        # 监控磁盘IO
        print(f"\n监控时长: {DEFAULT_MONITOR_DURATION}秒")
        print(f"采样间隔: {DEFAULT_SAMPLE_INTERVAL}秒")

        # 监控不同数据
        timestamps, total_read, total_write, read_speed, write_speed = monitor_disk_io(DEFAULT_MONITOR_DURATION,
                                                                                       DEFAULT_SAMPLE_INTERVAL)
        proc_timestamps, proc_read, proc_write = monitor_process_io(TARGET_PROCESS_NAME, DEFAULT_MONITOR_DURATION,
                                                                    DEFAULT_SAMPLE_INTERVAL)
        usage_timestamps, disk_usage_data = monitor_disk_usage(DEFAULT_MONITOR_DURATION, DEFAULT_SAMPLE_INTERVAL)
        dir_timestamps, directory_usage_data = monitor_directory_usage(DEFAULT_MONITOR_DURATION,
                                                                       DEFAULT_SAMPLE_INTERVAL, TARGET_DIRECTORIES)

        oslog_timestamps = []
        oslog_sizes = []
        if CURRENT_OS == "Darwin":
            print("\n监控macOS oslog日志...")
            oslog_timestamps, oslog_sizes = monitor_oslog(DEFAULT_MONITOR_DURATION, DEFAULT_SAMPLE_INTERVAL)

        # 生成图表
        if timestamps:
            generate_io_chart(timestamps, total_read, total_write, read_speed, write_speed, proc_read, proc_write)
        if usage_timestamps:
            generate_disk_usage_chart(usage_timestamps, disk_usage_data)
        if dir_timestamps:
            generate_directory_usage_chart(dir_timestamps, directory_usage_data)
        if oslog_timestamps:
            generate_oslog_chart(oslog_timestamps, oslog_sizes)

        print("\n监控完成，图表已生成")
    except KeyboardInterrupt:
        print("\n监控被用户中断，正在生成图表...")
        # 生成图表
        if 'timestamps' in locals() and timestamps:
            generate_io_chart(timestamps, total_read, total_write, read_speed, write_speed, proc_read, proc_write)
        if 'usage_timestamps' in locals() and usage_timestamps:
            generate_disk_usage_chart(usage_timestamps, disk_usage_data)
        if 'dir_timestamps' in locals() and dir_timestamps:
            generate_directory_usage_chart(dir_timestamps, directory_usage_data)
        if 'oslog_timestamps' in locals() and oslog_timestamps:
            generate_oslog_chart(oslog_timestamps, oslog_sizes)

        print("图表已生成")


if __name__ == "__main__":
    main()

