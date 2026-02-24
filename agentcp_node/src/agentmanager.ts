import { IAgentCP, IAgentWS, IConnectionConfig } from './interfaces';
import { AgentCP } from './agentcp';
import { AgentWS } from './agentws';

class AgentManager {
    private static instance: AgentManager;
    private agentCP: IAgentCP | null = null;
    private agentWS: IAgentWS | null = null;

    private constructor() {}

    public static getInstance(): AgentManager {
        if (!AgentManager.instance) {
            AgentManager.instance = new AgentManager();
        }
        return AgentManager.instance;
    }

    public initACP(apiUrl: string, seedPassword: string = "", basePath?: string, options?: { persistMessages?: boolean }): IAgentCP {
        const acp = new AgentCP(apiUrl, seedPassword, basePath, options);
        this.agentCP = acp;
        return acp;
    }

    public initAWS(aid: string, config: IConnectionConfig): IAgentWS {
        const { messageServer, messageSignature } = config;
        this.agentWS = new AgentWS(aid, messageServer, messageSignature);
        return this.agentWS;
    }

    public acp(): IAgentCP {
        if (!this.agentCP) {
            throw new Error("AgentCP未初始化");
        }
        return this.agentCP;
    }

    public aws(): IAgentWS {
        if (!this.agentWS) {
            throw new Error("AgentWS未初始化");
        }
        return this.agentWS;
    }
}

export { AgentManager };