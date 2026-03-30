def setup_custom_openapi(app):
    original_openapi = app.openapi
    
    def openapi():
        if app.openapi_schema:
            return app.openapi_schema
        
        # 调用原始的openapi方法获取schema
        openapi_schema = original_openapi()
        
        # 确保所有schemas都有详细的描述和示例
        for schema_name, schema in openapi_schema.get("components", {}).get("schemas", {}).items():
            # 添加更多描述信息
            if "properties" in schema:
                for prop_name, prop in schema["properties"].items():
                    # 确保每个属性都有描述
                    if "description" not in prop and "title" not in prop:
                        prop["description"] = f"字段: {prop_name}"
                    # 确保每个属性都有示例值
                    if "example" not in prop and "examples" not in prop:
                        # 根据类型设置默认示例值
                        if prop.get("type") == "string":
                            prop["example"] = f"示例{prop_name}"
                        elif prop.get("type") == "integer":
                            prop["example"] = 1
                        elif prop.get("type") == "number":
                            prop["example"] = 1.0
                        elif prop.get("type") == "boolean":
                            prop["example"] = True
        
        app.openapi_schema = openapi_schema
        return app.openapi_schema
    
    app.openapi = openapi
