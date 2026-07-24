import re

with open('d:/program/chat/backend/app/routers/chat.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
'''                        try:
                            kv_store.delete(item["id"])
                        except Exception:
                            pass''',
'''                        try:
                            kv_store.delete(item["id"])
                        except Exception as e:
                            logger.warning(f"Failed to delete pending plan {item['id']}: {e}")'''
)

content = content.replace(
'''            except Exception:
                pass''',
'''            except Exception as e:
                logger.warning(f"Error processing pending plan approval: {e}")'''
)

content = content.replace(
'''                except Exception:
                    pass''',
'''                except Exception as e:
                    logger.warning(f"Failed to save plan approval request to KV store: {e}")'''
)

content = content.replace(
'''                    except:
                        pass''',
'''                    except Exception as e:
                        logger.warning(f"Failed to parse thinking_json for spec_document: {e}")'''
)

with open('d:/program/chat/backend/app/routers/chat.py', 'w', encoding='utf-8') as f:
    f.write(content)
