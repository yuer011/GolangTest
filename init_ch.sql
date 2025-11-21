CREATE DATABASE IF NOT EXISTS corplink;
USE corplink;
-- . AGW 访问日志表
CREATE TABLE corplink.agw_access_log (
    `tenant_id` String COMMENT '租户ID',
    `uid` Int32 COMMENT '用户ID',
    `email` String COMMENT '邮箱',
    `mobile` String COMMENT '手机号',
    `sip` String COMMENT '源IP',
    `sport` String COMMENT '源端口',
    `protocol` String COMMENT '协议',
    `scheme` String COMMENT 'https,http',
    `method` String COMMENT '请求方法',
    `host` String COMMENT '应用请求Host字段',
    `intranet_ip` String COMMENT '网关内网IP',
    `uri` String COMMENT '请求资源',
    `level` String COMMENT '日志级别',
    `status` Int32 COMMENT '状态码',
    `size` Int32 COMMENT '请求大小(byte)',
    `duration` Float64 COMMENT '请求往返时间(ms)',
    `timestamp` Int64 COMMENT '请求时间(s)',
    `user_agent` String COMMENT 'User agent',
    `referer` String COMMENT '来源地址',
    `req_body` String COMMENT '请求体',
    `resp_body` String COMMENT '响应体',
    `option` String,
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `forward_proxy` Bool DEFAULT false COMMENT '日志来源是否为正向代理',
    `open_id` String COMMENT '用户OpenID',
    `timestamp_ms` Int64 COMMENT '访问时间ms',
    `api_group_ids` Array(Int32) COMMENT 'API资源管理IDs',
    `log_type` Int8 COMMENT '0:app_control, 1:web_filter',
    `app_id` String COMMENT 'app id',
    `app_category_ids` Array(String) COMMENT 'app category id list',
    `strategy_id` Int64 COMMENT 'strategy id',
    `trigger_keys` Array(String) COMMENT 'trigger keys',
    `department_id_path` String COMMENT 'department id path',
    `trace_id` String COMMENT 'trace id',
    `did` String COMMENT '设备ID'
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (tenant_id, timestamp)
TTL toDate(timestamp) + toIntervalDay(180)
SETTINGS index_granularity = 8192;


-- . AI 聊天日志表
CREATE TABLE corplink.ai_chat_log (
    `tenant_id` String COMMENT '租户ID',
    `uid` Int64 COMMENT '用户ID',
    `bot_open_id` String COMMENT 'BotOpenID',
    `conversation_id` String COMMENT '对话ID',
    `message_id` String COMMENT '消息ID',
    `trace_id` String COMMENT 'TraceID',
    `human_content` String COMMENT '用户输入',
    `plugin_content` String COMMENT '插件内容',
    `plugin_name` String COMMENT '插件名称',
    `log_type` String COMMENT '日志类型',
    `error_msg` String COMMENT '错误信息',
    `duration` Int64 COMMENT '时间间隔',
    `plugin_invoke` Int64 COMMENT '插件调用数',
    `first_response_duration` Int64 COMMENT '第一次SSE返回时间',
    `timestamp` Int64 COMMENT '请求时间(s)',
    `option` String COMMENT 'Option',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9))
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (tenant_id, timestamp)
TTL toDate(timestamp) + toIntervalDay(180)
SETTINGS index_granularity = 8192;


-- . AI DLP 分析事件表
CREATE TABLE corplink.ai_dlp_analysis_event (
    `tenant_id` String COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `tag` String COMMENT '场景标签',
    `period` String COMMENT '分析周期',
    `user_id` Int32 COMMENT '用户 ID',
    `device_id` String COMMENT 'Device ID',
    `event_id` String COMMENT '事件ID',
    `timestamp` Int64 COMMENT '事件时间',
    `file_hash` String COMMENT '文件hash',
    `file_name` String COMMENT 'file name',
    `file_type` String COMMENT 'file type',
    `leak_app_key` String COMMENT '外发应用',
    `leak_site_key` String COMMENT '外发网站',
    `data_key` String COMMENT '敏感数据标签',
    `data_level` String COMMENT '敏感数据密级'
) ENGINE = ReplacingMergeTree
PARTITION BY user_id % 1000
ORDER BY (tenant_id, event_id, user_id, tag, period)
TTL toDate(((create_time / 1000) / 1000) / 1000) + toIntervalDay(180)
SETTINGS index_granularity = 8192;


-- . AI DLP 分析文件表
CREATE TABLE corplink.ai_dlp_analysis_file (
    `tenant_id` String COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `tag` String COMMENT '场景标签',
    `period` String COMMENT '分析周期',
    `user_id` Int32 COMMENT '用户 ID',
    `device_id` String COMMENT 'Device ID',
    `node_id` String COMMENT '文件ID',
    `timestamp` Int64 COMMENT '文件创建/变更时间',
    `file_hash` String COMMENT '文件hash',
    `file_name` String COMMENT 'file name',
    `file_type` String COMMENT 'file type',
    `app_key` String COMMENT '创建应用key',
    `site_key` String COMMENT '创建site key',
    `data_keys` Array(String) COMMENT '敏感数据标签',
    `data_levels` Array(String) COMMENT '敏感数据密级'
) ENGINE = ReplacingMergeTree
PARTITION BY user_id % 1000
ORDER BY (tenant_id, node_id, user_id, tag, period)
TTL toDate(((create_time / 1000) / 1000) / 1000) + toIntervalDay(30)
SETTINGS index_granularity = 8192;


-- . AI 消息表
CREATE TABLE corplink.ai_message (
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `tenant_id` String COMMENT '租户ID',
    `type` String COMMENT '信息类型',
    `content` String COMMENT '聊天内容',
    `error_msg` String COMMENT '报错内容',
    `conversation_id` String COMMENT '对话ID',
    `message_id` String COMMENT '消息ID',
    `sequence` Int32 COMMENT '消息顺序',
    `user_id` Int64 COMMENT '用户ID',
    `extra_content` String COMMENT 'extra content of message in JSON'
) ENGINE = MergeTree
PRIMARY KEY (message_id, conversation_id, user_id, content)
ORDER BY (message_id, conversation_id, user_id, content, sequence)
TTL toDate(create_time) + toIntervalDay(180)
SETTINGS index_granularity = 8192;


-- . 应用管控告警表
CREATE TABLE corplink.app_control_alarm (
    `tenant_id` String COMMENT '租户ID',
    `alarm_id` String DEFAULT generateUUIDv4(),
    `uid` Int32 COMMENT '用户ID',
    `did` String COMMENT '设备ID',
    `strategy_id` Int32 COMMENT '应用管控策略ID',
    `domain` String COMMENT '应用域名',
    `trigger_timestamp` Int64 COMMENT '触发时间',
    `timestamp` Int64 COMMENT '时间戳',
    `option` String,
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `trigger_content` String,
    `alarm_type` Int8 COMMENT '0:app_control, 1:web_filter',
    `url_category_id` String COMMENT 'url category id',
    `url_id` String COMMENT 'url id',
    `department_id_path` String COMMENT 'department id path',
    `trigger_keys` Array(String) COMMENT 'trigger keys',
    `full_url` String COMMENT 'full url including path'
) ENGINE = MergeTree
PARTITION BY toDate(trigger_timestamp)
ORDER BY (tenant_id, trigger_timestamp)
TTL toDate(timestamp) + toIntervalDay(180)
SETTINGS index_granularity = 8192;


-- . 终端安全事件表
CREATE TABLE corplink.av_event (
    `tenant_id` String COMMENT '租户 ID',
    `event_id` String COMMENT '事件 ID',
    `user_id` Int32 COMMENT '用户 ID',
    `user_email` String COMMENT '用户邮箱',
    `user_name` String COMMENT '用户名',
    `user_status` Int32 COMMENT '用户状态',
    `department_id_paths` String COMMENT '(多)部门路径',
    `device_id` String COMMENT '设备 ID',
    `device_ip` String COMMENT '设备 IP',
    `device_name` String COMMENT '设备名',
    `device_hostname` String COMMENT '设备主机名',
    `device_serial_number` String COMMENT '设备 SN 号',
    `device_os` String COMMENT '设备系统 win/mac/linux',
    `app_version` String COMMENT '客户端版本',
    `config_key` String COMMENT '配置 key',
    `config_name` String COMMENT '配置名',
    `config_version` String COMMENT '配置版本',
    `timestamp` Int64 COMMENT '事件发生时间',
    `report_time` DateTime COMMENT '事件上报时间',
    `scan_mode` String,
    `scan_scene` String,
    `scan_id` String,
    `threat_object_flag` String,
    `threat_object_id` String,
    `threat_file_path` String,
    `threat_file_hash` String,
    `threat_file_size` UInt64,
    `threat_file_type` String,
    `process_name` String,
    `threat_type` String,
    `raw_malware_name` String,
    `threat_level` Int32,
    `remediation` String,
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `app_build_number` String,
    `disposition_action` Int32,
    `detect_type` Int32,
    `detect_scene` Int32,
    `threat_file_digital_signature` String COMMENT '病毒文件签名',
    `threat_file_path_type` Int8 COMMENT '病毒文件路径类型',
    `virus_lib_version` String COMMENT '病毒库版本号',
    `trust_type` Int8 COMMENT '信任类型',
    `trust_data` String COMMENT '信任数据具体的值',
    `operator` Int8 COMMENT '信任类型',
    `engine_source` Int8 COMMENT '数据来源:0:无效数据,1:终端防病毒通用配置,2:文件威胁情报,3:比特凡特病毒引擎',
    `file_sha1` String COMMENT '文件sha1',
    `scan_type` Int8 DEFAULT 0 COMMENT '扫描类型',
    INDEX idx_event_id event_id TYPE bloom_filter GRANULARITY 3
) ENGINE = ReplacingMergeTree
PARTITION BY toDate(timestamp)
ORDER BY (timestamp, event_id)
TTL toDate(timestamp) + toIntervalMonth(6)
SETTINGS index_granularity = 8192;


-- . 病毒库更新日志表
CREATE TABLE corplink.av_lib_update_log (
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `updated_at_timestamp` Int64 COMMENT '病毒库更新时间戳',
    `version` Int64 COMMENT '病毒库更新后的版本',
    `status` Int8 COMMENT '病毒库更新状态 0-成功 其它-失败'
) ENGINE = MergeTree
PARTITION BY toDate(updated_at_timestamp)
ORDER BY updated_at_timestamp
TTL toDate(updated_at_timestamp) + toIntervalMonth(6)
SETTINGS index_granularity = 8192;


-- . 终端扫描任务表
CREATE TABLE corplink.av_scan_task (
    `tenant_id` String COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `task_id` String COMMENT '扫描任务 ID',
    `user_id` Int32 COMMENT '用户 ID',
    `device_id` String COMMENT '设备 ID',
    `config_key` String COMMENT '生效配置 key',
    `config_name` String COMMENT '生效配置名',
    `config_version` String COMMENT '生效策略的版本号',
    `task_type` Int8 COMMENT '任务类型',
    `start_time_ts` Int64 COMMENT '任务开始时间',
    `end_time_ts` Int64 COMMENT '任务结束时间戳'
) ENGINE = MergeTree
PARTITION BY toDate(start_time_ts)
ORDER BY start_time_ts
TTL toDate(start_time_ts) + toIntervalMonth(6)
SETTINGS index_granularity = 8192;


--  终端系统防御事件表
CREATE TABLE corplink.av_system_defense_event (
    `tenant_id` String,
    `event_id` String,
    `create_time` Int64,
    `user_id` Int32,
    `user_email` String,
    `user_name` String,
    `user_status` Int32,
    `department_id_paths` String,
    `device_id` String,
    `device_ip` String,
    `device_name` String,
    `device_hostname` String,
    `device_serial_number` String,
    `device_os` String,
    `app_version` String,
    `app_build_number` String,
    `config_key` String,
    `config_name` String,
    `config_version` String,
    `timestamp` Int64,
    `report_time` DateTime,
    `client_os_model` String,
    `client_os_detail_version` String,
    `event_type` Int32,
    `event_result` Int32,
    `config_action` UInt32,
    `disposal_type` UInt32,
    `operator` Int32,
    `source_process_id` UInt64,
    `source_process_cmd` String,
    `source_process_name` String,
    `source_process_path` String,
    `source_process_md5` String,
    `source_process_sha1` String,
    `source_process_size` UInt64,
    `source_process_signature` String,
    `target_script_name` String,
    `target_script_path` String,
    `target_script_md5` String,
    `target_script_sha1` String,
    `target_script_size` UInt64,
    `target_script_signature` String
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY timestamp
TTL toDate(timestamp) + toIntervalMonth(6)
SETTINGS index_granularity = 8192;


--  浏览器事件表
CREATE TABLE corplink.browser_event (
    `tenant_id` String COMMENT '租户 ID',
    `event_id` String COMMENT '事件 ID',
    `user_id` Int32 COMMENT '用户 ID',
    `user_email` String COMMENT '用户邮箱',
    `user_name` String COMMENT '用户名',
    `user_status` Int32 COMMENT '用户状态',
    `department_id_paths` String COMMENT '(多)部门路径',
    `device_id` String COMMENT '设备 ID',
    `device_ip` String COMMENT '设备 IP',
    `device_name` String COMMENT '设备名',
    `device_hostname` String COMMENT '设备主机名',
    `device_serial_number` String COMMENT '设备 SN 号',
    `device_os` String COMMENT '设备系统 win/mac/linux',
    `app_version` String COMMENT '客户端版本',
    `config_key` String COMMENT '配置 key',
    `config_name` String COMMENT '配置名',
    `config_version` String COMMENT '配置版本',
    `timestamp` Int64 COMMENT '事件发生时间',
    `report_time` DateTime COMMENT '事件上报时间',
    `event_type` String,
    `browser_type` String,
    `browser_name` String,
    `browser_version` String,
    `visit_url` String,
    `visit_title` String,
    `save_path` String,
    `file_size` UInt64,
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `app_build_number` String
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY timestamp
TTL toDate(timestamp) + toIntervalMonth(6)
SETTINGS index_granularity = 8192;


--  客户端指标表
CREATE TABLE corplink.client_metrics (
    `tenant_id` String COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `os` String COMMENT '设备系统 win/mac/linux',
    `app_version` String COMMENT '客户端版本',
    `event_time` Int64 COMMENT '事件发生时间',
    `did` String,
    `build_number` String,
    `dimension` String,
    `metric` String,
    `event_name` String
) ENGINE = MergeTree
PARTITION BY toDate(((create_time / 1000) / 1000) / 1000)
ORDER BY event_time
TTL toDate(((create_time / 1000) / 1000) / 1000) + toIntervalDay(15)
SETTINGS index_granularity = 8192;


--  CPE 连接跟踪日志表
CREATE TABLE corplink.cpe_conntrack_log (
    `tenant_id` String,
    `sip` String,
    `dip` String,
    `sport` Int32,
    `dport` Int32,
    `protocol` String,
    `host` String,
    `path` String,
    `action` String,
    `cpe_id` Int32,
    `timestamp` Int64,
    `option` String,
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `dst_address` String COMMENT '目标地址'
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (tenant_id, timestamp)
TTL toDate(timestamp) + toIntervalDay(30)
SETTINGS index_granularity = 8192;


--  定时任务事件表
CREATE TABLE corplink.cron_event (
    `tenant_id` String COMMENT '租户 ID,全局任务写入-',
    `event_id` String COMMENT '事件 ID',
    `job_key` String COMMENT '定时任务的唯一键,每种任务的都是相同的',
    `job_id` String COMMENT '定时任务的键，带有租户信息',
    `start_time` DateTime COMMENT '任务启动时间',
    `end_time` DateTime COMMENT '任务结束时间',
    `duration` UInt32 COMMENT '执行时间,单位是毫秒',
    `timeout` UInt32 COMMENT '当时配置的超时时间，单位是秒',
    `instance` String COMMENT '执行实例的ID',
    `status` UInt8 COMMENT '执行任务结果 0成功 1失败 2超时 3panic',
    `error` String COMMENT '失败的错误信息',
    `timestamp` Int64 COMMENT '上报时间',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9))
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (tenant_id, timestamp)
TTL toDate(timestamp) + toIntervalDay(14)
SETTINGS index_granularity = 8192;


--  设备诊断报告表
CREATE TABLE corplink.device_diagnostic_report (
    `tenant_id` String COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `timestamp` Int64 COMMENT '时间戳',
    `option` String COMMENT '日志操作类型',
    `report_key` String COMMENT 'report UUID',
    `content` String COMMENT 'JSON representation of diagnostic report',
    `load_data` String COMMENT 'JSON representation of load information data',
    `report_source` Int8 COMMENT '1 - cron triggered, 2 - bot triggered',
    `uid` Int32 COMMENT 'User ID',
    `did` String COMMENT 'Device DID',
    `report_status` Int8 COMMENT '0 - normal, 1 - marked',
    `expiry` Int64 COMMENT 'report expiry in unix time, 30 days from creation'
) ENGINE = ReplacingMergeTree
PARTITION BY toDate(create_time / ((1000 * 1000) * 1000))
ORDER BY (tenant_id, did, report_key, create_time)
TTL toDate(((create_time / 1000) / 1000) / 1000) + toIntervalDay(30)
SETTINGS index_granularity = 8192;


--  设备网络监控应用表
CREATE TABLE corplink.device_network_monitor_app (
    `tenant_id` String COMMENT '租户 ID',
    `timestamp` Int64 COMMENT '时间戳',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '记录创建时间',
    `option` String COMMENT '日志操作类型',
    `day_id` Int32 COMMENT '天数切片',
    `hour_id` Int32 COMMENT '小时切片',
    `time_id` Int32 COMMENT '5分钟切片',
    `deploy_mode` Int8 COMMENT '是否为云vpn',
    `loss` Int32 COMMENT '丢包率',
    `delay` Int32 COMMENT '延迟',
    `pop_id` Int32 COMMENT 'pop id',
    `vpn_id` Int32 COMMENT 'vpn id',
    `uid` String COMMENT 'uid',
    `did` String COMMENT 'did',
    `app_id` Int32 COMMENT '应用 id',
    `app_name` String COMMENT '应用名称'
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY timestamp
TTL toDate(timestamp) + toIntervalDay(3)
SETTINGS index_granularity = 8192;


--  设备进程服务表（替换表）
CREATE TABLE corplink.device_process_service_replace (
    `tenant_id` String COMMENT '租户id',
    `did` String COMMENT '设备did',
    `uid` Int64 COMMENT '用户id',
    `os` String COMMENT '操作系统',
    `app_ver` String COMMENT '飞连版本',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '记录创建时间',
    `report_time` Int64 COMMENT '数据上报时间',
    `process_name` Array(String) COMMENT '进程名称',
    `process_detail` Array(String) COMMENT '进程详情',
    `process_cpu` Array(Float64) COMMENT '进程 CPU 使用率',
    `process_memory` Array(Int32) COMMENT '进程内存占用，单位为MB',
    `startup_service_name` Array(String) COMMENT '启动服务名称',
    `startup_service_detail` Array(String) COMMENT '启动服务详情',
    `critical_service_name` Array(String) COMMENT '关键服务名称',
    `critical_service_detail` Array(String) COMMENT '关键服务详情'
) ENGINE = ReplacingMergeTree(report_time)
PARTITION BY cityHash64(did) % 100
ORDER BY (tenant_id, did)
TTL toDate(report_time) + toIntervalDay(20)
SETTINGS index_granularity = 8192
COMMENT '设备进程及服务表';


--  设备响应任务日志表
CREATE TABLE corplink.device_response_task_log (
    `tenant_id` String COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '记录创建时间',
    `timestamp` Int64 COMMENT '事件发生时间',
    `did` String COMMENT '设备did',
    `log_type` Int8 COMMENT '日志类型,0 管理员操作,1 设备响应',
    `operator_type` Int8 COMMENT '操作人类型,0 管理员,1 openapi',
    `operator_id` Int64 COMMENT 'operator id',
    `task_id` String COMMENT '任务id',
    `task_type` String COMMENT '任务类型',
    `status` Int8 COMMENT '状态',
    `mark` String COMMENT '标记',
    `args` String COMMENT '参数',
    `result` String COMMENT '结果',
    `extra` String COMMENT '额外信息',
    `error_code` Int64 COMMENT '错误码'
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (timestamp, did)
TTL toDate(timestamp) + toIntervalDay(180)
SETTINGS index_granularity = 8192
COMMENT '设备响应任务日志';


--  设备软件表（替换表）
CREATE TABLE corplink.device_software_replace (
    `tenant_id` String COMMENT '租户',
    `ver` Int64 COMMENT '版本号',
    `created_at` Int32 COMMENT '创建时间',
    `update_time` Int32 COMMENT '更新时间',
    `installed_at` Int32 COMMENT '安装时间',
    `uninstalled_at` Int32 COMMENT '卸载时间',
    `install_path` String COMMENT '安装路径',
    `software_version` String COMMENT '软件版本',
    `software_version_id` Int32 COMMENT '软件版本id',
    `did` String COMMENT '设备',
    `device_os` String COMMENT '设备系统',
    `sid` Int32 COMMENT '软件id',
    `software_name` String COMMENT '软件名称',
    `publisher` String COMMENT '发布者',
    `bundle_id` String COMMENT 'bundle_id',
    `user_id` Int32 COMMENT '用户id',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9))
) ENGINE = ReplacingMergeTree(ver)
PARTITION BY tenant_id
ORDER BY (tenant_id, sid, did)
SETTINGS index_granularity = 8192;


--  设备漏洞表（替换表）
CREATE TABLE corplink.device_vul_replace (
    `tenant_id` String COMMENT '租户',
    `ver` Int64 COMMENT '版本号',
    `created_at` Int32 COMMENT '创建时间',
    `updated_at` Int32 COMMENT '更新时间',
    `deleted_at` Int32 COMMENT '删除时间',
    `repaired_at` Int32 COMMENT '修复时间',
    `vul_status` Int8 COMMENT '修复状态',
    `did` LowCardinality(String) COMMENT '设备',
    `cve` LowCardinality(String) COMMENT 'cve',
    `threat_level` Int8 COMMENT '风险等级[1:紧急,2:高危,3:中危,4:低危,5:未知]'
) ENGINE = ReplacingMergeTree(ver)
PARTITION BY xxHash32(did) % 8
ORDER BY (tenant_id, cve, did)
SETTINGS index_granularity = 8192;


--  DNS 访问日志表
CREATE TABLE corplink.dns_access_log (
    `tenant_id` String COMMENT '租户ID',
    `request_id` String COMMENT '请求ID',
    `client_ip` String COMMENT '客户端IP地址',
    `version` String COMMENT 'DNS Request的版本',
    `user_open_id` String COMMENT '请求方用户的open_id',
    `device_id` String COMMENT '设备ID',
    `domain` String COMMENT '应用域名',
    `app_id` String COMMENT '应用id',
    `app_category_id` String COMMENT '应用分类id',
    `rcode` Int64 COMMENT 'RCode',
    `error_msg` String COMMENT '错误信息',
    `option` String,
    `timestamp` Int64 COMMENT '日志产生时间',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `log_type` Int8 COMMENT '0:app_control, 1:web_filter',
    `department_view_id` UInt64 COMMENT 'department id to aggregate on the dashboard'
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (tenant_id, timestamp)
TTL toDate(timestamp) + toIntervalDay(30)
SETTINGS index_granularity = 8192;


--  DNS 访问日志统计表
CREATE TABLE corplink.dns_access_log_stats (
    `day` Date,
    `tenant_id` String,
    `domain` String,
    `visits` AggregateFunction(count, UInt64),
    `visitors` AggregateFunction(uniq, String),
    `devices` AggregateFunction(uniq, String),
    `categories` AggregateFunction(anyLast, String)
) ENGINE = AggregatingMergeTree
ORDER BY (day, tenant_id, domain)
TTL day + toIntervalDay(180)
SETTINGS index_granularity = 8192;





--  动态规则事件表
CREATE TABLE corplink.dynamic_rule_event (
    `id` String,
    `tenant_id` String,
    `trigger_key` String,
    `group_id` Int32,
    `rule_id` Int32,
    `rule_version` String,
    `event_id` String,
    `undo` Int8,
    `is_manual` Int8,
    `result` Int32,
    `user_id` Int32,
    `did` String,
    `event_context` String,
    `action_key` String,
    `params` String,
    `created_at` Int64,
    `expired_at` Int64,
    `operator_id` Int32,
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9))
) ENGINE = MergeTree
PARTITION BY toYYYYMM(toDate(created_at))
PRIMARY KEY (tenant_id, group_id, rule_id)
ORDER BY (tenant_id, group_id, rule_id, created_at)
TTL toDate(created_at) + toIntervalMonth(6)
SETTINGS index_granularity = 8192;


--  动态规则触发事件表
CREATE TABLE corplink.dynamic_rule_trigger_event (
    `id` String COMMENT '唯一键',
    `tenant_id` String COMMENT '租户id',
    `created_at` DateTime COMMENT '创建时间',
    `updated_at` Nullable(DateTime) COMMENT '更新时间',
    `group_id` Int32 COMMENT '规则组id',
    `group_ver` Int32 COMMENT '规则组版本',
    `did` String COMMENT '设备did',
    `user_id` Int32 COMMENT '用户id',
    `trigger_key` String COMMENT '触发方式的key',
    `context` String COMMENT '触发上下文，json格式',
    `event_type` Int32 COMMENT '类型,[1:命中规则，存在处置, 2:未命中规则，存在恢复(不展示), 3: 未命中规则，存在恢复(展示), 4:未命中规则，触发日志]',
    `result` String COMMENT '规则的命中结果 map[rule_id]是否命中',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '写入时间'
) ENGINE = MergeTree
PARTITION BY toDate(created_at)
ORDER BY (tenant_id, created_at)
TTL toDate(created_at) + toIntervalMonth(6)
SETTINGS index_granularity = 8192;


--  EDLP 智能体分析反馈表
CREATE TABLE corplink.edlp_agent_analyze_feedback (
    `tenant_id` String COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '记录创建时间',
    `workflow` Int16 COMMENT '工作流ID',
    `knowledge_id` String COMMENT '智能体返回的结果关联ID',
    `target_user_id` Int32 COMMENT '目标用户ID',
    `target_device_id` String COMMENT '目标设备ID',
    `feedback_user_id` Int32 COMMENT '发起反馈的用户ID',
    `event_id` String COMMENT 'EDLP事件ID或综合分析范围ID',
    `feedback` String COMMENT '用户反馈内容 JSON'
) ENGINE = ReplacingMergeTree
PARTITION BY toDate(create_time / 1000000000.)
ORDER BY (tenant_id, event_id, workflow, target_user_id)
TTL toDate(create_time / 1000000000.) + toIntervalDay(180)
SETTINGS index_granularity = 8192;


--  EDLP 智能体分析文件表
CREATE TABLE corplink.edlp_agent_analyze_file (
    `tenant_id` String COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '记录创建时间',
    `user_id` Int32 COMMENT '用户ID',
    `event_id` String COMMENT 'edlp 事件ID',
    `timestamp` Int64 COMMENT 'edlp 事件发生时间',
    `file_name` String COMMENT '文件名称',
    `knowledge_id` String COMMENT '智能体返回的结果关联ID',
    `history_knowledge_id` Array(String) COMMENT '关联的历史分析结果',
    `data_type` Int16 COMMENT '数据类型',
    `data_class` String COMMENT '数据分类',
    `data_level` String COMMENT '数据分级',
    `pre_data_type` Int16 COMMENT '数据类型（修正前）',
    `pre_data_class` String COMMENT '数据分类（修正前）',
    `pre_data_level` String COMMENT '数据分级（修正前）',
    `file_topic_zh` String COMMENT '文件主题（中文）',
    `file_topic_en` String COMMENT '文件主题（英文）',
    `file_digest_zh` String COMMENT '文件摘要（中文）',
    `file_digest_en` String COMMENT '文件摘要（英文）',
    `reason_zh` String COMMENT '判断依据（中文）',
    `reason_en` String COMMENT '判断依据（英文）',
    `analyze_status` Int8 COMMENT 'AI分析状态 1=失败 2=成功 3=已修正',
    `error_code` String COMMENT '智能体错误码',
    `error_message` String COMMENT '错误信息'
) ENGINE = ReplacingMergeTree
PARTITION BY user_id % 100
ORDER BY (tenant_id, event_id)
TTL toDate(create_time / 1000000000.) + toIntervalDay(180)
SETTINGS index_granularity = 8192;


--  EDLP 智能体分析洞察表
CREATE TABLE corplink.edlp_agent_analyze_insight (
    `tenant_id` String COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '记录创建时间',
    `analyze_start_time` Int64 COMMENT '分析开始时间',
    `analyze_end_time` Int64 COMMENT '分析结束时间',
    `uuid` String COMMENT '飞连生成的行 id',
    `knowledge_id` String COMMENT '智能体返回的结果关联ID',
    `history_knowledge_id` Array(String) COMMENT '关联的历史分析结果',
    `user_id` Int32 COMMENT '用户ID',
    `event_start_time` Int64 COMMENT '开始时间',
    `event_end_time` Int64 COMMENT '结束时间',
    `event_count` Int32 COMMENT '事件数量',
    `risk_status` Int8 COMMENT 'AI结果,1: 存在泄密风险,2: 无风险,3: 可疑',
    `feedback_risk_status` Int8 COMMENT '反馈,0: 无反馈, 1: 存在泄密风险, 2: 确认无风险',
    `result_summary_zh` String COMMENT 'AI结果总结,json格式',
    `result_think_zh` String COMMENT 'AI思考过程,json格式',
    `result_summary_en` String COMMENT 'AI结果总结,json格式',
    `result_think_en` String COMMENT 'AI思考过程,json格式',
    `critical_analyze_zh` Array(String) COMMENT '关键异常分析,json格式',
    `critical_analyze_en` Array(String) COMMENT '关键异常分析,json格式',
    `analyze_context` String COMMENT '分析上下文数据',
    `analyze_status` Int8 COMMENT 'AI分析状态 1=失败 2=成功 3=已修正',
    `analyze_event_ids` Array(String) COMMENT '分析的事件id',
    `error_code` String COMMENT '智能体错误码',
    `error_message` String COMMENT '错误信息'
) ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMMDD(toDate(analyze_end_time))
ORDER BY (tenant_id, analyze_end_time, user_id)
TTL toDate(create_time / 1000000000.) + toIntervalDay(180)
SETTINGS index_granularity = 8192
COMMENT 'EDLP分析洞察结果表';


--  EDLP 分析洞察标记表
CREATE TABLE corplink.edlp_agent_analyze_insight_mark (
    `tenant_id` String COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '记录创建时间',
    `event_id` String COMMENT 'DLP事件ID',
    `event_timestamp` Int64 COMMENT 'DLP事件ID对应的时间',
    `knowledge_id` String COMMENT '智能体返回的结果关联ID',
    `risk_status` Int8 COMMENT '标记状态 1: 存在泄密风险, 2: 确认无风险'
) ENGINE = MergeTree
PARTITION BY toDate(event_timestamp)
ORDER BY (tenant_id, event_id)
TTL toDate(event_timestamp) + toIntervalDay(180)
SETTINGS index_granularity = 8192
COMMENT '风险洞察已处理事件标记';


--  EDLP 智能体分析截图表
CREATE TABLE corplink.edlp_agent_analyze_screenshot (
    `tenant_id` String COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '记录创建时间',
    `user_id` Int32 COMMENT '用户ID',
    `event_id` String COMMENT 'edlp 事件ID',
    `timestamp` Int64 COMMENT 'edlp 事件发生时间',
    `knowledge_id` String COMMENT '智能体返回的结果关联ID',
    `history_knowledge_id` Array(String) COMMENT '关联的历史分析结果',
    `screenshot_count` Int16 COMMENT '用于分析的截图数量',
    `operation_type` Int16 COMMENT '操作类型 enums',
    `flow_direction` Int16 COMMENT '流转方向 enums',
    `pre_operation_type` Int16 COMMENT '操作类型 enums（修正前）',
    `pre_flow_direction` Int16 COMMENT '流转方向 enums（修正前）',
    `target_type` Int16 COMMENT '流转目标类型 enums',
    `target_value` String COMMENT '流转目标',
    `operation_type_reason_zh` String COMMENT '操作类型-判断依据（中文）',
    `operation_type_reason_en` String COMMENT '操作类型-判断依据（英文）',
    `flow_direction_reason_zh` String COMMENT '流转方向-判断依据（中文）',
    `flow_direction_reason_en` String COMMENT '流转方向-判断依据（英文）',
    `target_value_reason_zh` String COMMENT '流转目标-判断依据（中文）',
    `target_value_reason_en` String COMMENT '流转目标-判断依据（英文）',
    `analyze_status` Int8 COMMENT 'AI分析状态 1=失败 2=成功 3=已修正',
    `error_code` String COMMENT '智能体错误码',
    `error_message` String COMMENT '错误信息'
) ENGINE = ReplacingMergeTree
PARTITION BY user_id % 100
ORDER BY (tenant_id, event_id)
TTL toDate(create_time / 1000000000.) + toIntervalDay(180)
SETTINGS index_granularity = 8192;


--  EDLP 阻断事件表
CREATE TABLE corplink.edlp_block_event (
    `tenant_id` String COMMENT '租户 ID',
    `event_id` String COMMENT '事件 ID',
    `user_id` Int32 COMMENT '用户 ID',
    `user_email` String COMMENT '用户邮箱',
    `user_name` String COMMENT '用户名',
    `user_status` Int32 COMMENT '用户状态',
    `department_id_paths` String COMMENT '(多)部门路径',
    `device_id` String COMMENT '设备 ID',
    `device_ip` String COMMENT '设备 IP',
    `device_name` String COMMENT '设备名',
    `device_hostname` String COMMENT '设备主机名',
    `device_serial_number` String COMMENT '设备 SN 号',
    `device_os` String COMMENT '设备系统 win/mac/linux',
    `app_version` String COMMENT '客户端版本',
    `config_key` String COMMENT '配置 key',
    `config_name` String COMMENT '配置名',
    `config_version` String COMMENT '配置版本',
    `timestamp` Int64 COMMENT '事件发生时间',
    `report_time` DateTime COMMENT '事件上报时间',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '记录创建时间',
    `block_way` String,
    `block_way_name` String,
    `app_build_number` String,
    INDEX idx_event_id event_id TYPE bloom_filter GRANULARITY 3
) ENGINE = ReplacingMergeTree
PARTITION BY toDate(timestamp)
ORDER BY (timestamp, event_id)
TTL toDate(timestamp) + toIntervalMonth(6)
SETTINGS index_granularity = 8192;


--  EDLP 采集文件表
CREATE TABLE corplink.edlp_collection_file (
    `tenant_id` String COMMENT '租户 ID',
    `user_id` Int32 COMMENT '用户 ID',
    `device_id` String COMMENT 'Device ID',
    `node_id` String COMMENT 'Node ID',
    `file_hash` String COMMENT '文件hash',
    `file_name` String COMMENT 'file name',
    `file_path` String COMMENT 'file path',
    `file_size` UInt64 COMMENT 'file size',
    `file_extension` String COMMENT 'file extension',
    `first_found_time` UInt64 COMMENT '文件被发现的时间',
    `last_access_time` UInt64 COMMENT '该文件上一次被访问的时间',
    `lsh_hash` UInt64 COMMENT '局部敏感哈希，默认为simhash',
    `is_dir` Bool COMMENT '是否为目录',
    `mime_type` String COMMENT '文件的mime_type名称，空字符串表示类型未知; 如果是目录，则该字段为空',
    `failed_to_extract_text` Bool COMMENT '标记暂时无法正确解析文档',
    `is_encrypted` Bool COMMENT 'is file encrypted boolean',
    `first_hash` String COMMENT '文件被第一次被观察到的时候，该文件的Hash',
    `source_flag` Int8 COMMENT '数据来源类型',
    `config_key` String COMMENT '采集策略Key',
    `config_name` String COMMENT '采集策略Name',
    `create_action` Int8 COMMENT '来源 action, 1 - 创建， 2 - 下载， 3 - 接收',
    `download_url` String COMMENT '如果该文件从浏览器下载，文件的下载url',
    `origin_url` String COMMENT '文件下载页面的url',
    `web_title` String COMMENT '网页标题',
    `created_process` String COMMENT '第一次写入该文件的进程名',
    `created_time` Int64 COMMENT '文件第一次被写入的时间 - unix',
    `app_key` String COMMENT '创建应用key',
    `app_type` String COMMENT '创建应用type',
    `site_key` String COMMENT '创建site key',
    `site_type` String COMMENT '创建site type',
    `modified_process` String COMMENT '上一次修改该文件的进程名',
    `modified_time` Int64 COMMENT '上一次修改该文件的时间',
    `is_all_tags_incredible` Bool COMMENT '文件的所有标签是否已经全部失效 / 文件是否被修改过',
    `data_keys` Array(String) COMMENT '敏感数据标签',
    `data_versions` Array(String) COMMENT '敏感数据标签对应版本',
    `data_levels` Array(String) COMMENT '敏感数据标签关联的数据密级',
    `report_time` DateTime COMMENT '上报时间',
    `timestamp` Int64 COMMENT 'event timestamp',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9))
) ENGINE = ReplacingMergeTree(source_flag)
PARTITION BY user_id % 1000
ORDER BY (tenant_id, device_id, node_id)
TTL toDate(report_time) + toIntervalDay(30)
SETTINGS index_granularity = 8192;


--  EDLP 采集文件上下文表
CREATE TABLE corplink.edlp_collection_file_context (
    `tenant_id` String COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '记录创建时间',
    `file_hash` String COMMENT 'file hash',
    `user_id` Int32 COMMENT 'user ID',
    `device_id` String COMMENT 'device ID',
    `node_id` String COMMENT 'file node ID for given device',
    `attr` UInt8 COMMENT '属性',
    `names` Array(String) COMMENT '命名匹配，例如模型和文件指纹',
    `match_type` UInt8 COMMENT '匹配类型',
    `match_value` String COMMENT '预期匹配内容',
    `match_times` UInt32 COMMENT '匹配次数',
    `match_pos` UInt32 COMMENT '上下文中的匹配开始位置',
    `match_len` UInt32 COMMENT '上下文中的匹配长度',
    `context` String COMMENT '匹配关联的上下文',
    `data_key` String COMMENT 'matched data keys',
    `data_version` String COMMENT 'matched data version'
) ENGINE = ReplacingMergeTree
PARTITION BY user_id % 1000
ORDER BY (tenant_id, device_id, node_id, data_key, attr, match_type, match_value, context)
TTL toDate(((create_time / 1000) / 1000) / 1000) + toIntervalDay(30)
SETTINGS index_granularity = 8192;


--  EDLP 采集文件流转表
CREATE TABLE corplink.edlp_collection_file_flow (
    `tenant_id` String,
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `serial` Int16 COMMENT '事件对应流转记录的序列号',
    `user_id` Int32 COMMENT 'user ID',
    `device_id` String COMMENT 'device ID',
    `node_id` String COMMENT 'file node ID for given device',
    `action` Int8 COMMENT '文件操作类型，枚举值',
    `timestamp` Int64 COMMENT '此次流转记录的发生时间',
    `app_key` String COMMENT '执行此操作的应用的key',
    `process_name` String COMMENT '执行此操作的应用的进程名',
    `site_key` String COMMENT '若为根节点且来源于浏览器，此项表示对应网站的 key',
    `site_title` String COMMENT '若为根节点且来源于浏览器，此项表示对应网站的标题',
    `site_url` String COMMENT '若为根节点且来源于浏览器，此项表示对应网站的链接',
    `source_node_file_id` Array(String) COMMENT '源节点的文件ID列表',
    `source_node_file_path` Array(String) COMMENT '源节点的文件路径列表',
    `dest_node_file_id` String COMMENT '目的节点的文件ID',
    `dest_node_file_path` String COMMENT '目的节点的文件路径'
) ENGINE = ReplacingMergeTree
PARTITION BY user_id % 1000
ORDER BY (tenant_id, device_id, node_id, timestamp, action)
TTL toDate(timestamp) + toIntervalDay(30)
SETTINGS index_granularity = 8192;


--  EDLP 事件表
CREATE TABLE corplink.edlp_event (
    `tenant_id` String COMMENT '租户 ID',
    `event_id` String COMMENT '事件 ID',
    `user_id` Int32 COMMENT '用户 ID',
    `user_email` String COMMENT '用户邮箱',
    `user_name` String COMMENT '用户名',
    `user_status` Int32 COMMENT '用户状态',
    `department_id_paths` String COMMENT '(多)部门路径',
    `device_id` String COMMENT '设备 ID',
    `device_ip` String COMMENT '设备 IP',
    `device_name` String COMMENT '设备名',
    `device_hostname` String COMMENT '设备主机名',
    `device_serial_number` String COMMENT '设备 SN 号',
    `device_os` String COMMENT '设备系统 win/mac/linux',
    `app_version` String COMMENT '客户端版本',
    `config_key` String COMMENT '配置 key',
    `config_name` String COMMENT '配置名',
    `config_version` String COMMENT '配置版本',
    `timestamp` Int64 COMMENT '事件发生时间',
    `report_time` DateTime COMMENT '事件上报时间',
    `leak_way_type` String,
    `leak_way_name` String,
    `leak_browser_url` String,
    `leak_browser_title` String,
    `leak_file_path` String,
    `leak_file_type` String,
    `leak_file_name` String,
    `leak_file_md5` String,
    `leak_file_size` UInt64,
    `leak_file_extension` String,
    `leak_file_creation_ts` UInt64,
    `leak_file_last_modify_ts` UInt64,
    `sensitive_data` String,
    `detected_keywords` Array(String),
    `detected_sensitive_data_info` Array(String),
    `leak_code_user_email` String,
    `leak_code_user_name` String,
    `leak_code_local_path` String,
    `leak_code_remote_url` String,
    `leak_code_repo_name` String,
    `data_key` String,
    `data_version` String,
    `data_level` String,
    `data_match` UInt64,
    `data_type` String,
    `filename_context` Array(String),
    `content_context` Array(String),
    `trigger_action` UInt64,
    `report_reason_type` Int32,
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `app_build_number` String,
    `leak_site_key` String,
    `leak_origin_type` Int8,
    `leak_origin_key` String,
    `leak_origin_timestamp` Int64,
    `leak_origin_title` String,
    `leak_origin_url` String,
    `file_flow_flag` Int8 COMMENT '文件流转节点标记',
    `fingerprint_ids` Array(UInt32) COMMENT '文件指纹ID',
    `fingerprint_similarities` Array(Int8) COMMENT '文件指纹相似度',
    `more_ext_info` String,
    `source_type` Int8 COMMENT '外发方式分类',
    `leak_file_found_ts` UInt64 COMMENT '文件首次发现时间',
    `leak_file_node_id` String COMMENT '泄露文件的本地 node ID',
    `leak_file_xxhash` String DEFAULT '' COMMENT '泄漏文件的XXHash',
    `store_node_id` Int64 COMMENT '存储节点ID',
    `leak_way_site_type` String COMMENT 'leak way type of website',
    `associate_tags` String DEFAULT '[]' COMMENT '关联的敏感数据标签, SetAssociateSensitiveDataTags 方法设置, GetAssociateSensitiveDataTags 方法获取',
    `ai_recognize_algorithm` Array(String) COMMENT 'AI识别算法',
    `ai_recognize_model` Array(Int32) COMMENT 'AI识别模型ID',
    `ai_recognize_label` Array(Int32) COMMENT 'AI识别标签ID',
    `ai_recognize_score` Array(Float64) COMMENT 'AI识别相似度',
    INDEX idx_event_id event_id TYPE bloom_filter GRANULARITY 3
) ENGINE = ReplacingMergeTree
PARTITION BY toDate(timestamp)
ORDER BY (timestamp, event_id)
TTL toDate(timestamp) + toIntervalMonth(6)
SETTINGS index_granularity = 8192;


--  EDLP 事件上下文表
CREATE TABLE corplink.edlp_event_context (
    `tenant_id` String COMMENT '租户 ID',
    `event_id` String COMMENT '事件 ID',
    `timestamp` Int64 COMMENT '事件发生时间',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '记录创建时间',
    `attr` UInt8 COMMENT '属性',
    `match_type` UInt8 COMMENT '匹配类型',
    `match_value` String COMMENT '预期匹配内容',
    `match_times` UInt32 COMMENT '匹配次数',
    `match_pos` UInt32 COMMENT '上下文中的匹配开始位置',
    `match_len` UInt32 COMMENT '上下文中的匹配长度',
    `context` String COMMENT '匹配关联的上下文',
    `user_id` Int32 COMMENT '用户 ID',
    `device_id` String COMMENT 'Device ID',
    `data_rule_key` String COMMENT '敏感数据规则key',
    `data_level` String COMMENT '敏感数据级别',
    `data_level_name` String COMMENT '敏感数据级别名称',
    `data_matched_key` UInt64 COMMENT '事件命中信息,由 owEvent.DlpEventMatchedKeys 中的按位与组合而来,组合规则 1<< EVENT_MATCHED_FILE_NAME | 1 << EVENT_MATCHED_FILE_EXTENSION ...',
    `data_rule_version` String COMMENT '敏感数据规则版本',
    `fingerprint_ids` Array(UInt32) COMMENT '命中的文件指纹ID',
    `fingerprint_similarities` Array(Int8) COMMENT '命中的文件指纹相似度',
    `origin_file_create_timestamp` Int64 COMMENT '文件创建/接收/下载时间戳',
    `leak_origin_type` Int8 COMMENT '泄露来源类型 1-web 2-app',
    `leak_origin_key` String COMMENT '泄露来源 key，标识应用或网站',
    `origin_web_key` String COMMENT 'web应用的web_key',
    `origin_web_title` String COMMENT '来源标题',
    `origin_web_url` String COMMENT '来源url',
    `origin_app_key` String COMMENT '桌面应用的app_key',
    `data_type` UInt8 DEFAULT 1 COMMENT '数据类型 1-直接命中的敏感上下文 2-关联的敏感上下文'
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (tenant_id, timestamp)
TTL toDate(timestamp) + toIntervalMonth(6)
SETTINGS index_granularity = 8192;


--  EDLP 事件优化表
CREATE TABLE corplink.edlp_event_optimize (
    `tenant_id` String COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `create_date` Date DEFAULT toDate(now()),
    `event_id` String COMMENT '事件 ID',
    `user_id` Int32 COMMENT '用户 ID',
    `user_email` String COMMENT '用户邮箱',
    `user_name` String COMMENT '用户名',
    `device_id` String COMMENT '设备 ID',
    `device_os` String COMMENT '设备系统 win/mac/linux',
    `app_version` String COMMENT '客户端版本',
    `app_build_number` String COMMENT '客户端小版本号',
    `config_key` String COMMENT '配置 key',
    `timestamp` Int64 COMMENT '事件发生时间',
    `report_time` DateTime COMMENT '事件上报时间',
    `leak_way_type` String,
    `leak_way_name` String,
    `leak_browser_url` String,
    `leak_browser_title` String,
    `leak_file_path` String,
    `leak_file_type` String,
    `leak_file_name` String,
    `leak_file_md5` String,
    `leak_file_size` UInt64,
    `leak_file_extension` String,
    `leak_file_creation_ts` UInt64,
    `leak_file_last_modify_ts` UInt64,
    `leak_file_found_ts` UInt64 COMMENT '文件首次发现时间',
    `leak_file_node_id` String COMMENT '泄露文件的本地 node ID',
    `leak_file_xxhash` String DEFAULT '' COMMENT '泄漏文件的XXHash',
    `data_key` String,
    `data_version` String,
    `data_level` String,
    `data_match` UInt64,
    `data_type` String,
    `trigger_action` UInt64,
    `report_reason_type` Int32,
    `leak_site_key` String,
    `leak_origin_type` Int8,
    `leak_origin_key` String,
    `leak_origin_timestamp` Int64,
    `leak_origin_title` String,
    `leak_origin_url` String,
    `file_flow_flag` Int8 COMMENT '文件流转节点标记',
    `source_type` Int8 COMMENT '外发方式分类',
    `store_node_id` Int64 COMMENT '存储节点ID'
) ENGINE = ReplacingMergeTree
PARTITION BY create_date
ORDER BY (event_id, timestamp)
TTL toDate(timestamp) + toIntervalMonth(6)
SETTINGS index_granularity = 8192;


--  EDLP 事件物化视图



--  EDLP 事件标签表
CREATE TABLE corplink.edlp_event_tag (
    `tenant_id` String COMMENT '租户ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '记录创建时间',
    `user_id` Int32 COMMENT '事件对应的用户ID',
    `device_id` String COMMENT '事件对应的设备ID',
    `event_id` String COMMENT '事件ID',
    `event_timestamp` Int64 COMMENT '事件对应时间戳',
    `operator_id` String COMMENT '操作人ID',
    `risk` Int8 COMMENT '风险状态',
    `dispose` Int8 COMMENT '处置状态'
) ENGINE = ReplacingMergeTree(create_time)
PARTITION BY user_id % 1000
ORDER BY event_id
TTL toDate(((create_time / 1000) / 1000) / 1000) + toIntervalMonth(6)
SETTINGS index_granularity = 8192;


--  EDLP 文件流转表
CREATE TABLE corplink.edlp_file_flow (
    `tenant_id` String,
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `event_id` String COMMENT '文件流转记录关联的审计事件ID',
    `event_timestamp` Int64 COMMENT '文件流转记录关联的审计事件时间戳',
    `serial` Int16 COMMENT '事件对应流转记录的序列号',
    `action` Int8 COMMENT '文件操作类型，枚举值',
    `timestamp` Int64 COMMENT '此次流转记录的发生时间',
    `app_key` String COMMENT '执行此操作的应用的key',
    `process_name` String COMMENT '执行此操作的应用的进程名',
    `site_key` String COMMENT '若为根节点且来源于浏览器，此项表示对应网站的 key',
    `site_title` String COMMENT '若为根节点且来源于浏览器，此项表示对应网站的标题',
    `site_url` String COMMENT '若为根节点且来源于浏览器，此项表示对应网站的链接',
    `source_node_file_id` Array(String) COMMENT '源节点的文件ID列表',
    `source_node_file_path` Array(String) COMMENT '源节点的文件路径列表',
    `dest_node_file_id` String COMMENT '目的节点的文件ID',
    `dest_node_file_path` String COMMENT '目的节点的文件路径',
    `user_id` Int32 COMMENT '用户 ID',
    `device_id` String COMMENT 'Device ID'
) ENGINE = MergeTree
PARTITION BY toDate(event_timestamp)
ORDER BY (tenant_id, event_id)
TTL toDate(event_timestamp) + toIntervalMonth(6)
SETTINGS index_granularity = 8192;


--  EDLP 对象风险状态表
CREATE TABLE corplink.edlp_object_risk_status (
    `tenant_id` String COMMENT '租户ID',
    `object_type` Int8 COMMENT '1为风险事件、2为风险用户',
    `object_value` String COMMENT '用户ID ｜ edlp事件ID',
    `object_status` Int8 COMMENT '状态：1 有风险 ｜ 2 无风险或者忽略',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '记录创建时间'
) ENGINE = MergeTree
PARTITION BY toDate(((create_time / 1000) / 1000) / 1000)
ORDER BY object_value
TTL toDate(((create_time / 1000) / 1000) / 1000) + toIntervalMonth(6)
SETTINGS index_granularity = 8192;


--  EDR 运行状态表
CREATE TABLE corplink.edr_running_status (
    `tenant_id` String,
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `user_id` Int32 COMMENT '用户 ID',
    `device_id` String COMMENT 'Device ID',
    `status_type` Int32 COMMENT '类型',
    `message` String COMMENT '消息',
    `event_size` Int64 COMMENT '事件大小',
    `event_type` String COMMENT '事件类型'
) ENGINE = MergeTree
PARTITION BY toDate(create_time / 1000000000.)
ORDER BY (tenant_id, device_id, status_type)
TTL toDate(create_time / 1000000000.) + toIntervalDay(15)
SETTINGS index_granularity = 8192;


--  EDR 威胁防护基础表（续）
CREATE TABLE corplink.edr_threat_protection_base (
    `tenant_id` String COMMENT '租户 ID',
    `event_id` String COMMENT '事件 uuid',
    `create_time` Int64 COMMENT '记录创建时间',
    `user_id` Int32 COMMENT '用户 ID',
    `user_email` String COMMENT '用户邮箱',
    `user_name` String COMMENT '用户名',
    `user_status` Int32 COMMENT '用户状态',
    `department_id_paths` String COMMENT '(多)部门 ID 路径',
    `device_id` String COMMENT '设备 ID',
    `device_ip` String COMMENT '设备 IP',
    `device_name` String COMMENT '设备名',
    `device_hostname` String COMMENT '设备主机名',
    `device_serial_number` String COMMENT '设备的 SN 号',
    `device_os` String COMMENT '设备的操作系统 win/mac/linux',
    `app_version` String COMMENT '客户端版本',
    `app_build_number` String COMMENT '客户端小版本号 build_number',
    `config_key` String COMMENT '策略/配置 key',
    `config_name` String COMMENT '策略/配置 名称',
    `config_version` String COMMENT '策略/配置 版本',
    `timestamp` Int64 COMMENT '客户端事件发生的时间戳',
    `report_time` DateTime COMMENT '接受上报事件的时间，Datetime 类型，用作表的 order by',
    `hit_rule_key` String COMMENT '命中的规则 key',
    `hit_rule_name` String COMMENT '命中的规则 名称',
    `behavior_type` String COMMENT '行为类型',
    `block` Bool COMMENT '是否阻断',
    `quarantine_file` Bool COMMENT '是否隔离文件',
    `source_process_name` String COMMENT '源进程名称',
    `source_process_path` String COMMENT '源进程路径',
    `target_process_path` String COMMENT '操作目标进程路径',
    `target_process_start_args` String COMMENT '操作目标进程参数'
) ENGINE = ReplacingMergeTree
PARTITION BY toDate(timestamp)
ORDER BY (tenant_id, timestamp, event_id)
TTL toDate(timestamp) + toIntervalMonth(6)
SETTINGS index_granularity = 8192;


--  员工审计日志表
CREATE TABLE corplink.employee_audit_log (
    `tenant_id` String COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '记录创建时间',
    `entry_id` Int64 COMMENT '操作者主键 ID',
    `entry_kind` Int32 COMMENT '操作者类型，0:未知 1:用户 2:应用 3:开放平台',
    `module` Int32 COMMENT '操作所属模块',
    `sub_module` Int32 COMMENT '操作所属子模块',
    `action` String COMMENT '执行动作',
    `ip` String COMMENT '操作者 IP',
    `client_info` String COMMENT '操作客户端信息',
    `success` Int8 COMMENT '操作是否成功',
    `events` String COMMENT '事件详情',
    `include_uid` String COMMENT '包含的用户 ID',
    `include_aid` String COMMENT '包含的事件 ID',
    `relate_key` String COMMENT '关联 Key',
    `app_version` String COMMENT '飞连客户端版本',
    `device_model` String COMMENT '设备型号'
) ENGINE = MergeTree
PARTITION BY toDate(((create_time / 1000) / 1000) / 1000)
ORDER BY (tenant_id, create_time, entry_id)
TTL toDate(((create_time / 1000) / 1000) / 1000) + toIntervalDay(365)
SETTINGS index_granularity = 8192
COMMENT '员工审计日志';


--  员工审计日志全量表
CREATE TABLE corplink.employee_audit_log_all (
    `tenant_id` String COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '记录创建时间',
    `entry_id` Int64 COMMENT '操作者主键 ID',
    `entry_kind` Int32 COMMENT '操作者类型，0:未知 1:用户 2:应用 3:开放平台',
    `module` Int32 COMMENT '操作所属模块',
    `sub_module` Int32 COMMENT '操作所属子模块',
    `action` String COMMENT '执行动作',
    `ip` String COMMENT '操作者 IP',
    `client_info` String COMMENT '操作客户端信息',
    `success` Int8 COMMENT '操作是否成功',
    `events` String COMMENT '事件详情',
    `include_uid` String COMMENT '包含的用户 ID',
    `include_aid` String COMMENT '包含的事件 ID',
    `relate_key` String COMMENT '关联 Key',
    `app_version` String COMMENT '飞连客户端版本',
    `device_model` String COMMENT '设备型号'
) ENGINE = MergeTree
PARTITION BY toDate(((create_time / 1000) / 1000) / 1000)
ORDER BY (tenant_id, create_time, entry_id)
SETTINGS index_granularity = 8192
COMMENT '员工审计日志全量数据，永久存储';





--  终端配置版本（客户端）表
CREATE TABLE corplink.endpoint_cfg_version_client (
    `tenant_id` String COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `update_time` Int64 COMMENT '更新时间',
    `device_id` Int64 COMMENT '设备ID',
    `version` String COMMENT '版本号',
    `config_type` String COMMENT '策略类型',
    `config_key` String COMMENT '策略key'
) ENGINE = ReplacingMergeTree(update_time)
PARTITION BY device_id % 50
ORDER BY (tenant_id, device_id, config_type, config_key)
TTL toDate(update_time) + toIntervalDay(60)
SETTINGS index_granularity = 8192;


--  终端配置版本（服务端）表
CREATE TABLE corplink.endpoint_cfg_version_server (
    `tenant_id` String COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `update_time` Int64 COMMENT '更新时间',
    `device_id` Int64 COMMENT '设备ID',
    `config_type` String COMMENT '策略类型',
    `config_key` String COMMENT '策略key'
) ENGINE = ReplacingMergeTree(update_time)
PARTITION BY device_id % 50
ORDER BY (tenant_id, device_id, config_type, config_key)
TTL toDateTime(update_time) + toIntervalHour(6)
SETTINGS index_granularity = 8192;


--  事件中心日志表
CREATE TABLE corplink.eventhub_log (
    `tenant_id` String COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '记录创建时间',
    `event_create_time` Int64 COMMENT '事件创建时间，毫秒',
    `entry_id` String COMMENT 'MQ 记录 ID',
    `event_id` String COMMENT '事件唯一ID, uuid',
    `event_type` String COMMENT '事件外发类型，如: user.v1.update',
    `event_inter_type` String COMMENT '内部真实事件类型',
    `event_detail` String COMMENT '事件详情'
) ENGINE = MergeTree
PARTITION BY toDate(((create_time / 1000) / 1000) / 1000)
ORDER BY (tenant_id, create_time)
TTL toDate(((create_time / 1000) / 1000) / 1000) + toIntervalDay(15)
SETTINGS index_granularity = 8192;


--  事件中心推送日志表
CREATE TABLE corplink.eventhub_push_log (
    `tenant_id` String COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '记录创建时间',
    `event_create_time` Int64 COMMENT '事件创建时间,毫秒',
    `event_id` String COMMENT '事件 ID',
    `event_type` String COMMENT '外发事件类型',
    `app_id` Int32 COMMENT '应用 ID',
    `app_open_id` String COMMENT '应用 OpenID',
    `hook_type` Int32 COMMENT '回调类型，1:webhook',
    `address` String COMMENT '推送地址',
    `status` Int8 COMMENT '推送状态, 1:成功 2:失败',
    `error_code` String COMMENT '错误码',
    `error_msg` String COMMENT '错误信息',
    `coast_time` Int32 COMMENT '推送耗时,毫秒',
    `retry_count` Int8 COMMENT '重试次数',
    `msg_detail` String COMMENT '推送消息详情'
) ENGINE = MergeTree
PARTITION BY toDate(((create_time / 1000) / 1000) / 1000)
ORDER BY (tenant_id, create_time, app_id, event_type, coast_time)
TTL toDate(((create_time / 1000) / 1000) / 1000) + toIntervalDay(7)
SETTINGS index_granularity = 8192;


--  事件中心推送重试日志表
CREATE TABLE corplink.eventhub_push_retry_log (
    `tenant_id` String COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '记录创建时间',
    `event_id` String COMMENT '事件 ID',
    `event_type` String COMMENT '事件类型',
    `app_id` Int32 COMMENT '应用 ID',
    `app_open_id` String COMMENT '应用 OpenID',
    `last_time` Int64 COMMENT '上次推送时间，毫秒',
    `next_time` Int64 COMMENT '下次推送时间，毫秒',
    `retry_count` Int8 COMMENT '重试次数,当前重试次数',
    `event_detail` String COMMENT '事件详情'
) ENGINE = MergeTree
PARTITION BY toDate(((create_time / 1000) / 1000) / 1000)
ORDER BY (tenant_id, next_time)
TTL toDate(((create_time / 1000) / 1000) / 1000) + toIntervalDay(7)
SETTINGS index_granularity = 8192;


--  EWF 事件表
CREATE TABLE corplink.ewf_event (
    `event_id` String COMMENT '事件 ID',
    `tenant_id` String COMMENT '租户id',
    `action_type` Int32 COMMENT '处置方式',
    `report_time` Int64 COMMENT '上报时间',
    `event_time` Int64 COMMENT '事件时间',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '记录创建时间',
    `uid` Int32 COMMENT '用户 id',
    `did` String COMMENT '设备 id',
    `site_source_type` Int8 COMMENT '站点类型',
    `site_id` Int64 COMMENT '站点 id',
    `category_source_type` Int8 COMMENT '分类类型',
    `category_id` Int32 COMMENT '分类 id',
    `url` String COMMENT 'URL 地址',
    `strategy_name` String COMMENT '策略名称',
    `strategy_key` String COMMENT '策略 key',
    `strategy_version` String COMMENT '策略版本',
    `os` String COMMENT '操作系统',
    `client_ip` String COMMENT '客户端 IP',
    `app_ver` Int32 COMMENT '客户端版本',
    `buildnumber` String COMMENT '客户端 buildnumber',
    `all_class_ids` Array(UInt64) COMMENT '所有命中的分类',
    `hit_class_id` UInt64 COMMENT '命中的分类',
    `department_id_paths` String COMMENT 'department id path'
) ENGINE = MergeTree
PARTITION BY toDate(event_time)
ORDER BY (tenant_id, event_time, did)
SETTINGS index_granularity = 8192;


--  数据导出事件表
CREATE TABLE corplink.export_event (
    `tenant_id` String COMMENT '租户 ID,全局任务写入-',
    `log_id` Int32 COMMENT '日志 ID',
    `rows` Int64 COMMENT '外发统计 - 行数',
    `total_bytes` Int64 COMMENT '外发统计 - 本次请求的总字节数',
    `max_bytes` Int64 COMMENT '外发统计 - 本次请求的最大单行字节数',
    `splits` Int32 COMMENT '外发统计 - 切分数',
    `next_cursor` Int64 COMMENT '下次外发的游标',
    `endpoint_types` Array(String) COMMENT '外发端类型',
    `endpoint_target` String COMMENT '外发端描述',
    `read_time` Int32 COMMENT '读取数据耗时，毫秒',
    `write_time` Int32 COMMENT '写入数据耗时，毫秒',
    `error` String COMMENT '失败的错误信息',
    `timestamp` Int64 COMMENT '外发时间',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `message` String COMMENT '附加信息',
    `log_key` String COMMENT '日志标识key',
    `progress` String COMMENT '读取进度'
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (tenant_id, timestamp)
TTL toDate(timestamp) + toIntervalDay(30)
SETTINGS index_granularity = 8192;


--  防火墙日志表
CREATE TABLE corplink.firewall (
    `event_id` String COMMENT '事件ID',
    `tenant_id` String COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `user_id` Int32 COMMENT '用户ID',
    `device_id` String COMMENT '设备id',
    `device_os` String COMMENT '设备os',
    `app_version` String COMMENT '飞连客户端版本号',
    `app_build_number` String COMMENT '飞连客户端小版本号',
    `config_key` String COMMENT '命中策略的key',
    `config_name` String COMMENT '命中策略的name（上报时）',
    `config_version` String COMMENT '命中策略的version',
    `timestamp` Int64 COMMENT '客户端事件发生事件',
    `report_time` Int64 COMMENT '服务端写入时间',
    `resource_keys` Array(String) COMMENT '命中的网络资源key',
    `remote_ip` String COMMENT '远端 IP',
    `local_ip` String COMMENT '本地 ip',
    `remote_port` Int32 COMMENT '远端 port',
    `local_port` Int32 COMMENT '本地 port',
    `source_ip` String COMMENT '源IP',
    `dst_ip` String COMMENT '目的ip',
    `source_port` Int32 COMMENT '源port',
    `dst_port` Int32 COMMENT '目的端',
    `log_type` Int8 COMMENT '事件类型，IP DNS',
    `direction_type` Int8 COMMENT '流量方向',
    `protocol_type` Int8 COMMENT 'TCP/IP协议类型 0-未知;1-ICMP;2-TCP;3-UDP',
    `action_type` Array(Int8) COMMENT '动作类型:0-未知; 1-阻断; 2-审计; 3-DNS劫持',
    `dns_domain` String COMMENT 'DSN策略命中的域名值',
    `dns_addr` Array(String) COMMENT 'DNS 劫持',
    `dns_msg_type` Int32 COMMENT 'DNS 消息类型'
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY timestamp
TTL toDate(timestamp) + toIntervalDay(14)
SETTINGS index_granularity = 8192;


--  HTTP 签名验证日志表
CREATE TABLE corplink.httpsig_verify_log (
    `tenant_id` String COMMENT '租户ID',
    `create_time` Int64 COMMENT '创建时间,纳秒',
    `timestamp` Int64 COMMENT '时间戳,秒',
    `http_method` String COMMENT 'HTTP 请求方法',
    `request_url` String COMMENT '请求 URL',
    `request_query` String COMMENT '请求查询参数',
    `app_ver` Int32 COMMENT '客户端版本',
    `did` String COMMENT '设备唯一标识符',
    `uid` Int64 COMMENT '用户 ID',
    `http_status` UInt16 COMMENT 'HTTP 状态码',
    `policy` String COMMENT '策略名称',
    `sign_keyid` UInt64 COMMENT '签名密钥 ID',
    `sign_alg` String COMMENT '签名算法',
    `sign_timestamp` Int64 COMMENT '签名时间戳',
    `verify_result` Int8 COMMENT '验签结果',
    `action_type` Int8 COMMENT '处置方式 1:仅验证 2:验证并阻断'
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (tenant_id, timestamp)
TTL toDateTime(timestamp) + toIntervalDay(14)
SETTINGS index_granularity = 8192;


--  MCP 工具调用日志表
CREATE TABLE corplink.mcp_tool_call_log (
    `tenant_id` String COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '记录创建时间',
    `timestamp` Int64 COMMENT 'Tool调用时间',
    `knowledge_id` String COMMENT '智能体返回的结果关联ID',
    `workflow` Int8 COMMENT '工作流, 1: 分类分级, 2: 截屏, 3: 风险洞察',
    `task_id` Int64 COMMENT 'edlp_agent_analyze_task 主键id',
    `tool_key` String COMMENT '工具 Key',
    `input` String COMMENT '输入, 参数 json',
    `output` String COMMENT '输出, 结果 json',
    `status_code` Int64 COMMENT '状态码,0:成功, 1:异常, 2:错误',
    `error_message` String COMMENT '错误信息',
    `duration_ms` Int64 COMMENT '耗时, ms'
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (tenant_id, knowledge_id)
TTL toDate(timestamp) + toIntervalDay(180)
SETTINGS index_granularity = 8192
COMMENT 'mcp 工具调用记录';


--  密码迁移日志表
CREATE TABLE corplink.password_migration_log (
    `tenant_id` String COMMENT '租户 ID',
    `timestamp` Int64 COMMENT '分区时间戳',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '时间戳：纳秒',
    `option` String COMMENT '日志操作类型',
    `uid` Int32 COMMENT '用户 ID',
    `password_migration_status` Int32 COMMENT '密码迁移状态 (0:未迁移, 1:迁移失败, 2:迁移成功)'
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY timestamp
TTL toDate(timestamp) + toIntervalMonth(6)
SETTINGS index_granularity = 8192;


--  外设事件表
CREATE TABLE corplink.peripheral_event (
    `tenant_id` String COMMENT '租户 ID',
    `event_id` String COMMENT '事件 ID',
    `user_id` Int32 COMMENT '用户 ID',
    `user_email` String COMMENT '用户邮箱',
    `user_name` String COMMENT '用户名',
    `user_status` Int32 COMMENT '用户状态',
    `department_id_paths` String COMMENT '(多)部门路径',
    `device_id` String COMMENT '设备 ID',
    `device_ip` String COMMENT '设备 IP',
    `device_name` String COMMENT '设备名',
    `device_hostname` String COMMENT '设备主机名',
    `device_serial_number` String COMMENT '设备 SN 号',
    `device_os` String COMMENT '设备系统 win/mac/linux',
    `app_version` String COMMENT '客户端版本',
    `config_key` String COMMENT '配置 key',
    `config_name` String COMMENT '配置名',
    `config_version` String COMMENT '配置版本',
    `timestamp` Int64 COMMENT '事件发生时间',
    `report_time` DateTime COMMENT '事件上报时间',
    `event_type` String,
    `peripheral_name` String,
    `peripheral_type` String,
    `peripheral_perm` String,
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `app_build_number` String,
    `vid` String DEFAULT '' COMMENT 'peripheral vid',
    `pid` String DEFAULT '' COMMENT 'peripheral pid',
    `serial` String DEFAULT '' COMMENT 'peripheral serial',
    INDEX idx_event_id event_id TYPE bloom_filter GRANULARITY 3
) ENGINE = ReplacingMergeTree
PARTITION BY toDate(timestamp)
ORDER BY (timestamp, event_id)
TTL toDate(timestamp) + toIntervalMonth(6)
SETTINGS index_granularity = 8192;


--  设备漏洞修复事件表
CREATE TABLE corplink.pm_device_vul_repair_event (
    `id` Int32 COMMENT '设备与漏洞记录id',
    `tenant_id` String COMMENT '租户ID',
    `cve` String COMMENT '漏洞编号',
    `did` String COMMENT '设备号',
    `threat_level` Int32 COMMENT '漏洞等级',
    `repaired_at` DateTime COMMENT '设备与漏洞记录修复时间',
    `created_at` DateTime COMMENT '设备与漏洞记录创建时间',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '记录创建时间'
) ENGINE = MergeTree
PARTITION BY toDate(((create_time / 1000) / 1000) / 1000)
ORDER BY create_time
TTL toDate(((create_time / 1000) / 1000) / 1000) + toIntervalMonth(6)
SETTINGS index_granularity = 8192;


--  进程控制审计表
CREATE TABLE corplink.process_control_audit (
    `tenant_id` String DEFAULT '00000000' COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '创建时间',
    `event_time` Int64 COMMENT '触发时间',
    `timestamp` Int64 COMMENT '创建时间戳',
    `did` String COMMENT '设备DID',
    `uid` Int32 COMMENT '用户ID',
    `os` String COMMENT '操作系统',
    `strategy_key` String COMMENT '策略key',
    `strategy_name` String COMMENT '策略名称',
    `rule_id` Int64 DEFAULT 0 COMMENT '检测项ID',
    `app_ver` Int32 COMMENT '飞连version',
    `build_number` Int32 COMMENT '飞连build_number',
    `process_name` String COMMENT '进程名称',
    `signature` String COMMENT '签名',
    `process_path` String DEFAULT '' COMMENT '进程路径',
    `file_version` String DEFAULT '' COMMENT '文件版本',
    `product_name` String DEFAULT '' COMMENT '产品名称',
    `company_name` String DEFAULT '' COMMENT '公司名称',
    `product_version` String DEFAULT '' COMMENT '产品版本',
    `file_description` String DEFAULT '' COMMENT '文件说明',
    `original_file_name` String DEFAULT '' COMMENT '原始文件名',
    `internal_name` String DEFAULT '' COMMENT '内部名称',
    `product_code` String DEFAULT '' COMMENT '产品代码'
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (tenant_id, timestamp, did)
TTL toDate(timestamp) + toIntervalMonth(6)
SETTINGS index_granularity = 8192;


--  应用配置同步日志表
CREATE TABLE corplink.provisioning_log (
    `log_id` String COMMENT 'log uuid',
    `tenant_id` String COMMENT 'tenant ID',
    `triggered_at` UInt64 COMMENT 'triggered unix timestamp',
    `completed_at` UInt64 COMMENT 'completion unix timestamp',
    `task_status` UInt8 COMMENT 'status of completed task',
    `app_id` UInt64 COMMENT 'application ID',
    `response` String COMMENT 'provisioning request response body',
    `error_msg` String COMMENT 'error message from service provider',
    `status_code` UInt32 COMMENT 'HTTP status code',
    `fl_error_code` Int32 COMMENT 'feilian error code',
    `user_id` UInt64 COMMENT 'user ID',
    `provisioning_action` String COMMENT 'provisioning action: create, update, delete',
    `provisioning_mode` UInt8 COMMENT '0 - auto, 1 - manual',
    `manual_job_id` UInt64 COMMENT 'Job ID for bulk manual trigger',
    `resource_id` String COMMENT 'service provider resource ID',
    `field_map` String COMMENT 'JSON to log attribute changes',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '记录创建时间'
) ENGINE = MergeTree
PARTITION BY toDate(((create_time / 1000) / 1000) / 1000)
ORDER BY (tenant_id, completed_at, log_id)
TTL toDate(((create_time / 1000) / 1000) / 1000) + toIntervalDay(180)
SETTINGS index_granularity = 8192;


--  全局资源URL表（旧版）
CREATE TABLE corplink.resource_url_global_old (
    `create_time` Int64 COMMENT '创建时间',
    `url` String COMMENT '地址',
    `category_ids` Array(UInt64) COMMENT '分类id列表',
    INDEX idx_category_ids category_ids TYPE bloom_filter(0.01) GRANULARITY 3
) ENGINE = ReplacingMergeTree(create_time)
PARTITION BY category_ids
ORDER BY url
SETTINGS index_granularity = 8192;








--  软件安装审计表
CREATE TABLE corplink.software_install_audit (
    `id` UUID DEFAULT generateUUIDv4() COMMENT '唯一ID',
    `tenant_id` String DEFAULT '00000000' COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '创建时间',
    `event_time` Int64 DEFAULT 0 COMMENT '触发时间',
    `timestamp` Int64 COMMENT '创建时间戳',
    `did` String COMMENT '设备DID',
    `uid` Int32 COMMENT '用户ID',
    `os` String COMMENT '操作系统',
    `strategy_key` String COMMENT '策略key',
    `strategy_name` String COMMENT '策略名称',
    `detect_item_id` Int64 DEFAULT 0 COMMENT '检测项ID',
    `app_ver` Int32 COMMENT '飞连version',
    `build_number` Int32 COMMENT '飞连build_number',
    `is_block_install` Int8 DEFAULT 0 COMMENT '是否阻止安装',
    `file_name` String COMMENT '文件名称',
    `md5` String COMMENT 'MD5值',
    `directory_name` String DEFAULT '' COMMENT '目录名称',
    `file_signature` String DEFAULT '' COMMENT '文件签名',
    `product_name` String DEFAULT '' COMMENT '产品名称',
    `corporation_name` String DEFAULT '' COMMENT '企业名称',
    `product_version` String DEFAULT '' COMMENT '产品版本',
    `file_description` String DEFAULT '' COMMENT '文件说明',
    `origin_file_name` String DEFAULT '' COMMENT '原始文件名',
    `internal_name` String DEFAULT '' COMMENT '内部名称',
    `product_code` String DEFAULT '' COMMENT '产品代码',
    `bundle_path` String DEFAULT '' COMMENT 'Bundle 路径名',
    `bundle_id` String DEFAULT '' COMMENT 'Bundle ID',
    `bundle_version` String DEFAULT '' COMMENT 'Bundle版本',
    `pkg_path` String DEFAULT '' COMMENT '安装包路径',
    `pkg_id` String DEFAULT '' COMMENT '安装包ID'
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (tenant_id, timestamp, did)
TTL toDate(timestamp) + toIntervalMonth(6)
SETTINGS index_granularity = 8192;


--  软件使用统计表
CREATE TABLE corplink.software_statistic (
    `tenant_id` String COMMENT '租户',
    `timestamp` Int64 COMMENT '创建时间戳',
    `start_time` Int64 COMMENT '使用时长的开始时间，秒级别时间戳',
    `end_time` Int64 COMMENT '使用时长的结束时间，秒级别时间戳',
    `day_id` Int32 COMMENT '时区为Local时,从2023-01-01到当前的日期',
    `hour_id` Int32 COMMENT '一天内第几个小时',
    `uid` Int32 COMMENT '用户id',
    `did` String COMMENT '设备',
    `sid` Int32 COMMENT '软件id',
    `duration` Int64 COMMENT '时间间隔',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `time_zone` String DEFAULT '' COMMENT '时区'
) ENGINE = MergeTree
PARTITION BY toYYYYMM(toDate(timestamp))
ORDER BY (tenant_id, sid, uid, did, timestamp)
TTL toDate(timestamp) + toIntervalDay(30)
SETTINGS index_granularity = 8192;


--  同步任务日志表
CREATE TABLE corplink.sync_task_logs (
    `tenant_id` String COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '记录创建时间',
    `updated_at` Nullable(DateTime) COMMENT '更新时间',
    `task_id` String COMMENT '任务ID',
    `name` String COMMENT '更新对象的名称',
    `object_type` UInt8 COMMENT '对象(人员|部门|角色)',
    `action` UInt8 COMMENT '操作动作(创建|更新|删除)',
    `state` UInt8 COMMENT '操作结果(成功|异常|忽略)',
    `source_data` String COMMENT '原始数据',
    `target_data` String COMMENT '变更数据',
    `content` String COMMENT '详情',
    `third_party_union_id` String COMMENT '第三方唯一ID',
    `receive_time` DateTime COMMENT '事件接收时间',
    INDEX name_idx name TYPE ngrambf_v1(3, 256, 2, 0) GRANULARITY 4
) ENGINE = MergeTree
PARTITION BY toDate(((create_time / 1000) / 1000) / 1000)
ORDER BY (tenant_id, task_id, create_time)
TTL toDate(((create_time / 1000) / 1000) / 1000) + toIntervalDay(7)
SETTINGS index_granularity = 8192;


--  终端威胁防护表
CREATE TABLE corplink.ti_endpoint_protect (
    `tenant_id` String COMMENT '租户 ID',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `user_id` Int32 COMMENT '用户ID',
    `device_id` String COMMENT '设备id',
    `device_os` String COMMENT '设备os',
    `app_version` String COMMENT '飞连客户端版本号',
    `app_build_number` String COMMENT '飞连客户端小版本号',
    `timestamp` Int64 COMMENT '客户端事件发生事件',
    `report_time` Int64 COMMENT '服务端写入时间',
    `event_id` String COMMENT '事件ID',
    `target_domain` String COMMENT 'DSN策略命中的域名值',
    `dns_addresses` Array(String) COMMENT 'DNS解析的值',
    `remote_ip` String COMMENT '远端 IP',
    `remote_port` UInt32 COMMENT '远端 port',
    `local_ip` String COMMENT '本地 ip',
    `local_port` UInt32 COMMENT '本地 port',
    `protocol` Int8 COMMENT 'UDP/TCP',
    `risk_type` Int8 COMMENT '威胁类型',
    `action` Int8 COMMENT '动作类型'
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY timestamp
TTL toDate(timestamp) + toIntervalDay(180)
SETTINGS index_granularity = 8192;


--  威胁情报库更新日志表
CREATE TABLE corplink.ti_lib_update_log (
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `update_time` Int64 COMMENT '情报库更新时间',
    `version` String COMMENT '病毒库更新后的版本',
    `log_type` String COMMENT '日志类型',
    `err_code` Int8 COMMENT '错误码',
    `err_msg` String COMMENT '错误日志'
) ENGINE = MergeTree
PARTITION BY toDate(update_time)
ORDER BY update_time
TTL toDate(update_time) + toIntervalMonth(6)
SETTINGS index_granularity = 8192;


--  用户信息同步表
CREATE TABLE corplink.user_info_replicate (
    `id` Int32 COMMENT '用户id',
    `created_at` DateTime COMMENT '用户创建时间',
    `updated_at` DateTime COMMENT '用户更新时间',
    `deleted_at` DateTime COMMENT '用户删除时间',
    `tenant_id` String COMMENT '租户ID',
    `open_id` String COMMENT '用户open_id',
    `user_id` String COMMENT '第三方ID',
    `email` String COMMENT '用户email',
    `mobile` String COMMENT '用户手机号',
    `full_name` String COMMENT '用户名',
    `department_id` Int32 COMMENT '用户主部门id',
    `expire_at` DateTime COMMENT '用户账号过期时间',
    `status` Int32 COMMENT '账号状态',
    `enable_type` Int32,
    `icon_url` String,
    `pin_yin` String,
    `department_ids` Array(Int32) COMMENT '用户部门：包含所有父部门',
    `roles_list` String COMMENT '用户角色列表',
    `roles_list_arr` Array(Int32) COMMENT '用户角色列表',
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '记录创建时间'
) ENGINE = ReplacingMergeTree
ORDER BY id
TTL toDate(((create_time / 1000) / 1000) / 1000) + toIntervalDay(3)
SETTINGS index_granularity = 8192;


--  VPN 连接日志表
CREATE TABLE corplink.vpn_connect_log (
    `tenant_id` String,
    `did` String,
    `connect_time` Nullable(DateTime),
    `disconnect_time` Nullable(DateTime),
    `vpn_ip` String,
    `vpn_ipv6` String,
    `client_ip` String,
    `os` String,
    `device_model` String,
    `vpn_id` Int32,
    `app_version` String,
    `uid` Int32,
    `timestamp` Int64,
    `option` String,
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9))
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY timestamp
TTL toDate(timestamp) + toIntervalMonth(6)
SETTINGS index_granularity = 8192;


--  VPN 连接跟踪（按部门）物化视图
CREATE MATERIALIZED VIEW corplink.vpn_conntrack_application_depart_mv (
    `tenant_id` String,
    `timestamp` Int64,
    `depart_id` String,
    `dip` String,
    `dport` Int32,
    `protocol` String
) ENGINE = MergeTree
ORDER BY (tenant_id, timestamp, depart_id)
TTL toDate(timestamp) + toIntervalDay(30)
SETTINGS index_granularity = 8192
AS
SELECT
    tenant_id,
    timestamp,
    arrayJoin(depart_ids) AS depart_id,
    dip,
    dport,
    protocol
FROM corplink.vpn_conntrack_log;


--  VPN 连接跟踪（按角色）物化视图
CREATE MATERIALIZED VIEW corplink.vpn_conntrack_application_role_mv (
    `tenant_id` String,
    `timestamp` Int64,
    `role_id` String,
    `dip` String,
    `dport` Int32,
    `protocol` String
) ENGINE = MergeTree
ORDER BY (tenant_id, timestamp, role_id)
TTL toDate(timestamp) + toIntervalDay(30)
SETTINGS index_granularity = 8192
AS
SELECT
    tenant_id,
    timestamp,
    arrayJoin(role_ids) AS role_id,
    dip,
    dport,
    protocol
FROM corplink.vpn_conntrack_log;

--  VPN 统计表
CREATE TABLE corplink.vpn_statistic (
    `tenant_id` String,
    `timestamp` Int64,
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `option` String,
    `day_id` Int32,
    `hour_id` Int32,
    `time_id` Int32,
    `uid` Int32,
    `role_ids` Array(Int32),
    `depart_ids` Array(Int32),
    `duration` Int32,
    `rx` Int64,
    `tx` Int64
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY timestamp
TTL toDate(timestamp) + toIntervalDay(90)
SETTINGS index_granularity = 8192;


--  WiFi CoA 任务表
CREATE TABLE corplink.wifi_coa_tasks (
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)) COMMENT '创建时间',
    `timestamp` Int64 DEFAULT toUnixTimestamp(now()) COMMENT '时间戳',
    `option` String DEFAULT '' COMMENT '操作类型',
    `tenant_id` String DEFAULT '00000000' COMMENT '租户 ID',
    `start_time` DateTime DEFAULT now() COMMENT '任务开始时间',
    `connection_id` Int32 DEFAULT 0 COMMENT '网络连接 ID',
    `account_type` Int32 DEFAULT 0 COMMENT '连接类型',
    `device_id` String DEFAULT '' COMMENT '设备 did',
    `coa_info` String DEFAULT '' COMMENT 'CoA 任务信息',
    `radius_id` Int32 DEFAULT 0 COMMENT 'radius ID',
    `result_code` Int32 DEFAULT 0 COMMENT '任务结果',
    `reason_code` UInt8 DEFAULT 0 COMMENT '触发原因'
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY timestamp
TTL toDate(timestamp) + toIntervalMonth(6)
SETTINGS index_granularity = 8192
COMMENT 'CoA 任务事件日志';


--  WiFi 连接日志表
CREATE TABLE corplink.wifi_connect_log (
    `tenant_id` String,
    `connect_time` Nullable(DateTime),
    `disconnect_time` Nullable(DateTime),
    `connection_result` Int32,
    `connection_group_id` String,
    `connection_ip` String,
    `account_id` Int32,
    `account_username` String,
    `account_type` Int32,
    `device_id` String,
    `device_name` String,
    `calling_station_id` String,
    `called_station_id` String,
    `creators` String,
    `remarks` String,
    `timestamp` Int64,
    `option` String,
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `radius_id` Int32,
    `auth_account_type` Int32 COMMENT '入网凭据类型'
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY timestamp
TTL toDate(timestamp) + toIntervalMonth(6)
SETTINGS index_granularity = 8192;


--  WiFi 连接详情表
CREATE TABLE corplink.wifi_connection_log (
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `tenant_id` String,
    `connect_time` DateTime,
    `disconnect_time` DateTime,
    `connection_result` Int32,
    `connection_group_id` String,
    `connection_ip` String,
    `account_id` Int32,
    `account_username` String,
    `account_type` Int32,
    `auth_account_type` Int32,
    `portal_login_type` String,
    `device_id` String,
    `device_name` String,
    `calling_station_id` String,
    `called_station_id` String,
    `nas_identifier` String,
    `nas_ip` String,
    `creators` String,
    `remarks` String,
    `radius_id` Int32,
    `nas_id` Int32,
    `session_id` String,
    `ssid` String
) ENGINE = MergeTree
PARTITION BY toDate(connect_time)
ORDER BY connect_time
TTL connect_time + toIntervalMonth(6)
SETTINGS index_granularity = 8192;

--  VPN 连接跟踪（按用户）物化视图
CREATE MATERIALIZED VIEW corplink.vpn_conntrack_application_user_mv (
    `tenant_id` String,
    `timestamp` Int64,
    `uid` Int32,
    `dip` String,
    `dport` Int32,
    `protocol` String
) ENGINE = MergeTree
ORDER BY (tenant_id, timestamp, uid)
TTL toDate(timestamp) + toIntervalDay(30)
SETTINGS index_granularity = 8192
AS
SELECT
    tenant_id,
    timestamp,
    uid,
    dip,
    dport,
    protocol
FROM corplink.vpn_conntrack_log;


--  VPN 连接跟踪日志表
CREATE TABLE corplink.vpn_conntrack_log (
    `tenant_id` String,
    `uid` Int32,
    `depart_ids` Array(String),
    `role_ids` Array(String),
    `uip` String,
    `sip` String,
    `dip` String,
    `sport` Int32,
    `dport` Int32,
    `uport` Int32,
    `protocol` String,
    `host` String,
    `path` String,
    `action` String,
    `did` String,
    `smac` String,
    `mobile` String,
    `email` String,
    `os` String,
    `os_version` String,
    `device_brand` String,
    `device_model` String,
    `app_version` String,
    `timestamp` Int64,
    `option` String,
    `create_time` Int64 DEFAULT toUnixTimestamp64Nano(now64(9)),
    `resource_tag_ids` Array(Int32) COMMENT '[资源管理]资源标签ID',
    `process_status` UInt8 COMMENT '处理状态0-未处置，1-已处置',
    `dst_address` String COMMENT '目标地址',
    `app_discovery_enable` UInt8 COMMENT '是否开启应用发现0-未开启，1-已开启'
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY timestamp
TTL toDate(timestamp) + toIntervalDay(15)
SETTINGS index_granularity = 8192;


--  VPN 部门应用访问物化视图
CREATE MATERIALIZED VIEW corplink.vpn_department_app_visit_mv (
    `tenant_id` String,
    `dst_address` String,
    `dport` Int32,
    `protocol` String,
    `uid` Int32,
    `depart_id` String,
    `timestamp` Int64,
    `visits` UInt64
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (tenant_id, timestamp, uid, depart_id, dst_address)
TTL toDate(timestamp) + toIntervalDay(30)
SETTINGS index_granularity = 8192
AS
SELECT
    tenant_id,
    dst_address,
    dport,
    protocol,
    uid,
    arrayJoin(depart_ids) AS depart_id,
    max(timestamp) AS timestamp,
    count(dip) AS visits
FROM corplink.vpn_conntrack_log
GROUP BY tenant_id, uid, depart_id, dst_address, dport, protocol;


--  VPN 时长统计（按部门）物化视图
CREATE MATERIALIZED VIEW corplink.vpn_duration_depart_mv (
    `tenant_id` String,
    `day_id` Int32,
    `hour_id` Int32,
    `depart_id` Int32,
    `sum_duration` Int64
) ENGINE = SummingMergeTree
ORDER BY (tenant_id, depart_id, day_id, hour_id)
SETTINGS index_granularity = 8192
AS
SELECT
    tenant_id,
    day_id,
    hour_id,
    arrayJoin(depart_ids) AS depart_id,
    sum(duration) AS sum_duration
FROM corplink.vpn_statistic
GROUP BY tenant_id, depart_id, day_id, hour_id;


--  VPN 时长统计（按角色）物化视图
CREATE MATERIALIZED VIEW corplink.vpn_duration_role_mv (
    `tenant_id` String,
    `day_id` Int32,
    `hour_id` Int32,
    `role_id` Int32,
    `sum_duration` Int64
) ENGINE = SummingMergeTree
ORDER BY (tenant_id, role_id, day_id, hour_id)
SETTINGS index_granularity = 8192
AS
SELECT
    tenant_id,
    day_id,
    hour_id,
    arrayJoin(role_ids) AS role_id,
    sum(duration) AS sum_duration
FROM corplink.vpn_statistic
GROUP BY tenant_id, role_id, day_id, hour_id;


--  VPN 流量峰值（按部门）物化视图
CREATE MATERIALIZED VIEW corplink.vpn_peak_depart_mv (
    `tenant_id` String,
    `day_id` Int32,
    `hour_id` Int32,
    `depart_id` Int32,
    `sum_rx` Int64,
    `sum_tx` Int64
) ENGINE = SummingMergeTree
ORDER BY (tenant_id, depart_id, day_id, hour_id)
SETTINGS index_granularity = 8192
AS
SELECT
    tenant_id,
    day_id,
    hour_id,
    arrayJoin(depart_ids) AS depart_id,
    sum(rx) AS sum_rx,
    sum(tx) AS sum_tx
FROM corplink.vpn_statistic
GROUP BY tenant_id, depart_id, day_id, hour_id;


--  VPN 流量峰值（按角色）物化视图
CREATE MATERIALIZED VIEW corplink.vpn_peak_role_mv (
    `tenant_id` String,
    `day_id` Int32,
    `hour_id` Int32,
    `role_id` Int32,
    `sum_rx` Int64,
    `sum_tx` Int64
) ENGINE = SummingMergeTree
ORDER BY (tenant_id, role_id, day_id, hour_id)
SETTINGS index_granularity = 8192
AS
SELECT
    tenant_id,
    day_id,
    hour_id,
    arrayJoin(role_ids) AS role_id,
    sum(rx) AS sum_rx,
    sum(tx) AS sum_tx
FROM corplink.vpn_statistic
GROUP BY tenant_id, role_id, day_id, hour_id;


--  VPN 角色应用访问物化视图
CREATE MATERIALIZED VIEW corplink.vpn_role_app_visit_mv (
    `tenant_id` String,
    `dst_address` String,
    `dport` Int32,
    `protocol` String,
    `uid` Int32,
    `role_id` String,
    `timestamp` Int64,
    `visits` UInt64
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (tenant_id, timestamp, uid, role_id, dst_address)
TTL toDate(timestamp) + toIntervalDay(30)
SETTINGS index_granularity = 8192
AS
SELECT
    tenant_id,
    dst_address,
    dport,
    protocol,
    uid,
    arrayJoin(role_ids) AS role_id,
    max(timestamp) AS timestamp,
    count(dip) AS visits
FROM corplink.vpn_conntrack_log
GROUP BY tenant_id, uid, role_id, dst_address, dport, protocol;



--  软件使用时长（按天）物化视图
CREATE MATERIALIZED VIEW corplink.software_duration_day_mv (
    `tenant_id` String,
    `sid` Int32,
    `uid` Int32,
    `did` String,
    `day_id` Int32,
    `duration` Int64
) ENGINE = SummingMergeTree
PARTITION BY tenant_id
ORDER BY (tenant_id, sid, uid, did, day_id)
TTL (toDate('2023-01-01') + toIntervalDay(day_id)) + toIntervalDay(31)
SETTINGS index_granularity = 8192
AS
SELECT
    tenant_id,
    sid,
    uid,
    did,
    day_id,
    sum(duration) AS duration
FROM corplink.software_statistic
GROUP BY tenant_id, sid, uid, did, day_id;

CREATE MATERIALIZED VIEW corplink.dns_access_log_stats_mv
TO corplink.dns_access_log_stats (
    `day` Date,
    `tenant_id` String,
    `domain` String,
    `visits` AggregateFunction(count, UInt64),
    `visitors` AggregateFunction(uniq, String),
    `devices` AggregateFunction(uniq, String),
    `categories` AggregateFunction(anyLast, String)
) AS
SELECT
    toDate(timestamp) AS day,
    tenant_id AS tenant_id,
    domain AS domain,
    countState(toUInt64(1)) AS visits,
    uniqState(user_open_id) AS visitors,
    uniqState(device_id) AS devices,
    anyLastState(app_category_id) AS categories
FROM corplink.dns_access_log
WHERE log_type = 1
GROUP BY (toDate(timestamp), tenant_id, domain);

CREATE MATERIALIZED VIEW corplink.edlp_event_mv
TO corplink.edlp_event_optimize (
    `tenant_id` String,
    `create_time` Int64,
    `create_date` Date,
    `event_id` String,
    `user_id` Int32,
    `user_email` String,
    `user_name` String,
    `device_id` String,
    `device_os` String,
    `app_version` String,
    `app_build_number` String,
    `config_key` String,
    `timestamp` Int64,
    `report_time` DateTime,
    `leak_way_type` String,
    `leak_way_name` String,
    `leak_browser_url` String,
    `leak_browser_title` String,
    `leak_file_path` String,
    `leak_file_type` String,
    `leak_file_name` String,
    `leak_file_md5` String,
    `leak_file_size` UInt64,
    `leak_file_extension` String,
    `leak_file_creation_ts` UInt64,
    `leak_file_last_modify_ts` UInt64,
    `leak_file_found_ts` UInt64,
    `leak_file_node_id` String,
    `leak_file_xxhash` String,
    `data_key` String,
    `data_version` String,
    `data_level` String,
    `data_match` UInt64,
    `data_type` String,
    `trigger_action` UInt64,
    `report_reason_type` Int32,
    `leak_site_key` String,
    `leak_origin_type` Int8,
    `leak_origin_key` String,
    `leak_origin_timestamp` Int64,
    `leak_origin_title` String,
    `leak_origin_url` String,
    `file_flow_flag` Int8,
    `source_type` Int8,
    `store_node_id` Int64
) AS
SELECT
    tenant_id,
    create_time,
    toDate(create_time / 1000000000.) AS create_date,
    event_id,
    user_id,
    user_email,
    user_name,
    device_id,
    device_os,
    app_version,
    app_build_number,
    config_key,
    timestamp,
    report_time,
    leak_way_type,
    leak_way_name,
    leak_browser_url,
    leak_browser_title,
    leak_file_path,
    leak_file_type,
    leak_file_name,
    leak_file_md5,
    leak_file_size,
    leak_file_extension,
    leak_file_creation_ts,
    leak_file_last_modify_ts,
    leak_file_found_ts,
    leak_file_node_id,
    leak_file_xxhash,
    data_key,
    data_version,
    data_level,
    data_match,
    data_type,
    trigger_action,
    report_reason_type,
    leak_site_key,
    leak_origin_type,
    leak_origin_key,
    leak_origin_timestamp,
    leak_origin_title,
    leak_origin_url,
    file_flow_flag,
    source_type,
    store_node_id
FROM corplink.edlp_event;

--  员工审计日志物化视图（同步到全量表）
CREATE MATERIALIZED VIEW corplink.employee_audit_log_mv
TO corplink.employee_audit_log_all (
    `tenant_id` String,
    `create_time` Int64,
    `entry_id` Int64,
    `entry_kind` Int32,
    `module` Int32,
    `sub_module` Int32,
    `action` String,
    `ip` String,
    `client_info` String,
    `success` Int8,
    `events` String,
    `include_uid` String,
    `include_aid` String,
    `relate_key` String,
    `app_version` String,
    `device_model` String
) AS
SELECT
    tenant_id,
    create_time,
    entry_id,
    entry_kind,
    module,
    sub_module,
    action,
    ip,
    client_info,
    success,
    events,
    include_uid,
    include_aid,
    relate_key,
    app_version,
    device_model
FROM corplink.employee_audit_log;

--  软件使用时长（按小时）物化视图
CREATE MATERIALIZED VIEW corplink.software_duration_hour_mv (
    `tenant_id` String,
    `sid` Int32,
    `uid` Int32,
    `did` String,
    `day_id` Int32,
    `hour_id` Int32,
    `duration` Int64
) ENGINE = SummingMergeTree
PARTITION BY day_id
ORDER BY (tenant_id, sid, uid, did, day_id, hour_id)
TTL (toDate('2023-01-01') + toIntervalDay(day_id)) + toIntervalDay(31)
SETTINGS index_granularity = 8192
AS
SELECT
    tenant_id,
    sid,
    uid,
    did,
    day_id,
    hour_id,
    sum(duration) AS duration
FROM corplink.software_statistic
GROUP BY tenant_id, sid, uid, did, day_id, hour_id;

