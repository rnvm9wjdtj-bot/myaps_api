/**
 * 帮助中心页面脚本
 */

// 页面加载完成后执行
document.addEventListener('DOMContentLoaded', function() {
    // 初始化页面
    initHelpPage();
});

/**
 * 初始化帮助页面
 */
async function initHelpPage() {
    try {
        // 加载结构配置文件
        const structure = await loadStructure();
        
        // 动态生成导航菜单
        generateNavMenu(structure);
        
        // 动态生成内容
        generateContent(structure[0]); // 默认显示第一个菜单项的内容
        
        console.log('Help page initialized');
    } catch (error) {
        console.error('Failed to initialize help page:', error);
    }
}

/**
 * 加载结构配置文件
 */
async function loadStructure() {
    try {
        const response = await fetch('/help/api/structure');
        if (!response.ok) {
            throw new Error('Failed to load structure');
        }
        return await response.json();
    } catch (error) {
        console.error('Failed to load structure:', error);
        // 返回默认结构作为 fallback
        return [
            {
                "name": "首页",
                "header": "欢迎使用帮助中心",
                "description": "这里提供了产品的详细文档和使用指南，帮助您快速上手",
                "children": [
                    {
                        "name": "产品概述",
                        "url": "https://www.baidu.com",
                        "icon": "file-text",
                        "description": "了解产品的基本功能和特点，包括系统架构、核心功能和应用场景",
                        "updateAt": "2026-01-01"
                    }
                ]
            }
        ];
    }
}

/**
 * 动态生成导航菜单
 */
function generateNavMenu(structure) {
    const navMenu = document.querySelector('.nav-menu');
    if (!navMenu) return;
    
    // 清空现有菜单
    navMenu.innerHTML = '';
    
    // 生成菜单项
    structure.forEach((item, index) => {
        const li = document.createElement('li');
        li.className = 'nav-item';
        
        const a = document.createElement('a');
        a.href = '#';
        a.className = `nav-link ${index === 0 ? 'active' : ''}`;
        a.textContent = item.name;
        a.addEventListener('click', (event) => {
            event.preventDefault();
            handleNavClick(event, item);
        });
        
        li.appendChild(a);
        navMenu.appendChild(li);
    });
}

/**
 * 导航菜单点击事件处理
 */
function handleNavClick(event, menuItem) {
    // 移除所有活动状态
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.remove('active');
    });
    
    // 添加活动状态到当前点击的链接
    event.target.classList.add('active');
    
    // 生成对应内容
    generateContent(menuItem);
}

/**
 * 动态生成内容
 */
function generateContent(menuItem) {
    const contentHeader = document.querySelector('.content-header');
    const docGrid = document.querySelector('.doc-grid');
    
    if (!contentHeader || !docGrid) return;
    
    // 清空内容标题，避免重复显示导航栏中的标题
    contentHeader.innerHTML = '';
    
    // 清空现有内容
    docGrid.innerHTML = '';
    
    // 生成分组内容
    if (menuItem.groups && menuItem.groups.length > 0) {
        menuItem.groups.forEach(group => {
            // 创建分组容器
            const groupContainer = document.createElement('div');
            groupContainer.className = 'group-container';
            
            // 添加分组标题和描述
            groupContainer.innerHTML = `
                <div class="group-header">
                    <h3>${group.header}</h3>
                    <p>${group.description}</p>
                </div>
                <div class="group-content">
                </div>
            `;
            
            // 获取分组内容容器
            const groupContent = groupContainer.querySelector('.group-content');
            
            // 生成文档卡片
            if (group.children && group.children.length > 0) {
                group.children.forEach(child => {
                    const card = document.createElement('div');
                    card.className = 'doc-card';
                    
                    // 根据icon值生成对应的图标
                    const iconMap = {
                        'file-text': '📋',
                        'rocket': '🚀',
                        'code': '💻',
                        'help-circle': '❓'
                    };
                    const icon = iconMap[child.icon] || child.icon || '📄';
                    
                    card.innerHTML = `
                        <div class="doc-icon">${icon}</div>
                        <h4>${child.name}</h4>
                        <p>${child.description}</p>
                        <div class="doc-meta">
                            <span>更新时间: ${child.updateAt}</span>
                        </div>
                    `;
                    
                    // 添加点击事件，跳转到对应URL
                    if (child.url) {
                        card.style.cursor = 'pointer';
                        card.addEventListener('click', () => {
                            // 尝试创建一个更像弹窗的窗口，尽量最小化地址栏显示
                            window.open(child.url, '_blank', 'width=1000,height=700,toolbar=no,location=yes,menubar=no,scrollbars=yes,resizable=yes');
                        });
                    }
                    
                    groupContent.appendChild(card);
                });
            } else {
                // 无内容时显示空状态
                groupContent.innerHTML = `
                    <div class="empty-state">
                        <i>📄</i>
                        <p>暂无文档</p>
                    </div>
                `;
            }
            
            docGrid.appendChild(groupContainer);
        });
    } else {
        // 无内容时显示空状态
        docGrid.innerHTML = `
            <div class="empty-state">
                <i>📄</i>
                <p>暂无内容</p>
            </div>
        `;
    }
}