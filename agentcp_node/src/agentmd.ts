/**
 * agent.md 自动生成模块
 */

export interface AgentMdOptions {
    /** 代理ID */
    aid: string;
    /** 显示名称（可选，默认从 aid 提取） */
    name?: string;
    /** 代理类型（默认 "human"） */
    type?: string;
    /** 版本号（默认 "1.0.0"） */
    version?: string;
    /** 描述信息 */
    description?: string;
    /** 标签列表 */
    tags?: string[];
}

/**
 * 从 AID 中提取显示名称
 * 例如: "alice.agentcp.io" -> "alice"
 */
export function extractDisplayName(aid: string): string {
    const suffixes = ['.agentcp.io', '.agentid.pub'];
    for (const suffix of suffixes) {
        if (aid.endsWith(suffix)) {
            return aid.slice(0, -suffix.length);
        }
    }
    return aid;
}

/**
 * 生成 agent.md 内容
 */
export function generateAgentMd(options: AgentMdOptions): string {
    const {
        aid,
        name = extractDisplayName(aid),
        type = 'human',
        version = '1.0.0',
        description = `${name} 的个人主页`,
        tags = ['human', 'acp'],
    } = options;

    const tagsYaml = tags.map(t => `  - ${t}`).join('\n');

    return `---
aid: "${aid}"
name: "${name}"
type: "${type}"
version: "${version}"
description: "${description}"
tags:
${tagsYaml}
---

# ${name}

> ${description}

## About

This is the agent profile for **${name}** (${aid}).

- Type: ${type}
- Version: ${version}
`;
}
