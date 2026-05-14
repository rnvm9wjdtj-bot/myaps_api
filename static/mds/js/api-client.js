/**
 * @file api-client.js
 * @description API调用封装层 - 统一错误处理、请求拦截、响应格式化
 * @author Frontend Team
 * @version 1.0.0
 * @date 2026-05-14
 * @requires ./common.js
 */

class ApiClient {
    /**
     * 构造函数
     * @param {Object} options - 配置选项
     * @param {string} [options.baseUrl='/api/mds'] - API基础URL
     * @param {number} [options.timeout=30000] - 请求超时时间(ms)
     * @param {Object} [options.headers] - 默认请求头
     */
    constructor(options = {}) {
        this.baseUrl = options.baseUrl || '/api/mds';
        this.timeout = options.timeout || 30000;
        this.defaultHeaders = options.headers || {};
        this.requestInterceptors = [];
        this.responseInterceptors = [];
    }

    /**
     * 添加请求拦截器
     * @param {Function} interceptor - 拦截器函数 (config) => config
     */
    addRequestInterceptor(interceptor) {
        this.requestInterceptors.push(interceptor);
    }

    /**
     * 添加响应拦截器
     * @param {Function} interceptor - 拦截器函数 (response) => response
     */
    addResponseInterceptor(interceptor) {
        this.responseInterceptors.push(interceptor);
    }

    /**
     * 执行请求拦截
     * @param {Object} config - 请求配置
     * @returns {Object} 处理后的配置
     */
    async executeRequestInterceptors(config) {
        let result = { ...config };
        for (const interceptor of this.requestInterceptors) {
            result = await interceptor(result);
        }
        return result;
    }

    /**
     * 执行响应拦截
     * @param {Object} response - 响应对象
     * @returns {Object} 处理后的响应
     */
    async executeResponseInterceptors(response) {
        let result = { ...response };
        for (const interceptor of this.responseInterceptors) {
            result = await interceptor(result);
        }
        return result;
    }

    /**
     * 发起请求
     * @param {string} endpoint - API端点路径
     * @param {Object} [options] - 请求选项
     * @param {string} [options.method='GET'] - HTTP方法
     * @param {Object} [options.data] - 请求体数据
     * @param {Object} [options.params] - URL参数
     * @param {Object} [options.headers] - 额外请求头
     * @param {number} [options.timeout] - 超时时间
     * @returns {Promise<Object>} 响应数据
     */
    async request(endpoint, options = {}) {
        const {
            method = 'GET',
            data = null,
            params = null,
            headers = {},
            timeout = this.timeout
        } = options;

        // 构建完整URL
        let url = this.baseUrl + endpoint;
        
        // 处理URL参数
        if (params && typeof params === 'object') {
            const queryString = new URLSearchParams(params).toString();
            if (queryString) {
                url += (url.includes('?') ? '&' : '?') + queryString;
            }
        }

        // 构建请求配置
        const requestConfig = {
            method: method.toUpperCase(),
            headers: {
                'Content-Type': 'application/json',
                ...this.defaultHeaders,
                ...headers
            },
            signal: AbortController.timeout(timeout).signal
        };

        // 处理请求体
        if (data !== null && method !== 'GET' && method !== 'HEAD') {
            requestConfig.body = JSON.stringify(data);
        }

        // 执行请求拦截
        const processedConfig = await this.executeRequestInterceptors({
            url,
            ...requestConfig
        });

        try {
            const response = await fetch(url, processedConfig);

            // 解析响应
            let responseData;
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                responseData = await response.json();
            } else if (contentType && contentType.includes('text/')) {
                responseData = await response.text();
            } else {
                responseData = await response.blob();
            }

            // 执行响应拦截
            const result = await this.executeResponseInterceptors({
                success: response.ok ? 1 : 0,
                status: response.status,
                statusText: response.statusText,
                data: responseData,
                message: response.ok ? 'success' : (responseData?.message || response.statusText)
            });

            return result;

        } catch (error) {
            if (error.name === 'TimeoutError') {
                return {
                    success: 0,
                    status: 408,
                    message: '请求超时',
                    data: null
                };
            }
            if (error.name === 'TypeError' && error.message.includes('fetch')) {
                return {
                    success: 0,
                    status: 0,
                    message: '网络请求失败，请检查网络连接',
                    data: null
                };
            }
            return {
                success: 0,
                status: error.status || 500,
                message: error.message || '请求失败',
                data: null
            };
        }
    }

    /**
     * GET请求
     * @param {string} endpoint - API端点
     * @param {Object} [params] - URL参数
     * @param {Object} [options] - 额外选项
     * @returns {Promise<Object>} 响应数据
     */
    async get(endpoint, params = null, options = {}) {
        return this.request(endpoint, {
            method: 'GET',
            params,
            ...options
        });
    }

    /**
     * POST请求
     * @param {string} endpoint - API端点
     * @param {Object} [data] - 请求体数据
     * @param {Object} [options] - 额外选项
     * @returns {Promise<Object>} 响应数据
     */
    async post(endpoint, data = null, options = {}) {
        return this.request(endpoint, {
            method: 'POST',
            data,
            ...options
        });
    }

    /**
     * PUT请求
     * @param {string} endpoint - API端点
     * @param {Object} [data] - 请求体数据
     * @param {Object} [options] - 额外选项
     * @returns {Promise<Object>} 响应数据
     */
    async put(endpoint, data = null, options = {}) {
        return this.request(endpoint, {
            method: 'PUT',
            data,
            ...options
        });
    }

    /**
     * PATCH请求
     * @param {string} endpoint - API端点
     * @param {Object} [data] - 请求体数据
     * @param {Object} [options] - 额外选项
     * @returns {Promise<Object>} 响应数据
     */
    async patch(endpoint, data = null, options = {}) {
        return this.request(endpoint, {
            method: 'PATCH',
            data,
            ...options
        });
    }

    /**
     * DELETE请求
     * @param {string} endpoint - API端点
     * @param {Object} [options] - 额外选项
     * @returns {Promise<Object>} 响应数据
     */
    async delete(endpoint, options = {}) {
        return this.request(endpoint, {
            method: 'DELETE',
            ...options
        });
    }

    /**
     * 上传文件
     * @param {string} endpoint - API端点
     * @param {File} file - 文件对象
     * @param {Object} [params] - URL参数
     * @returns {Promise<Object>} 响应数据
     */
    async upload(endpoint, file, params = null) {
        let url = this.baseUrl + endpoint;
        
        if (params && typeof params === 'object') {
            const queryString = new URLSearchParams(params).toString();
            if (queryString) {
                url += (url.includes('?') ? '&' : '?') + queryString;
            }
        }

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch(url, {
                method: 'POST',
                body: formData,
                signal: AbortController.timeout(this.timeout).signal
            });

            const responseData = await response.json();

            return {
                success: response.ok ? 1 : 0,
                status: response.status,
                data: responseData.data,
                message: response.ok ? 'success' : (responseData.message || response.statusText)
            };
        } catch (error) {
            return {
                success: 0,
                status: 0,
                message: error.message || '文件上传失败',
                data: null
            };
        }
    }
}

// 创建全局实例
const apiClient = new ApiClient();

// 添加请求日志拦截器
apiClient.addRequestInterceptor(async (config) => {
    console.debug(`[API Request] ${config.method} ${config.url}`);
    return config;
});

// 添加响应日志拦截器
apiClient.addResponseInterceptor(async (response) => {
    console.debug(`[API Response] ${response.status} - ${response.message}`);
    return response;
});
