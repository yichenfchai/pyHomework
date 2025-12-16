

### 教师端：
- 使用测试账号登录：t1，密码:123。
- 可以查看学生信息、发布作业、查看学生作业完成情况。

### 学生端：
- 使用测试账号：s1或s2；密码：123。
- 可以注册、登录、上传word作业、预览和查看大模型评分、评分结果语音播放

## 使用方法

1、本地需创建存放本程序的环境变量的配置文件（.env），用于存放大模型的API KEY

在**项目的根目录**下，创建记事本，在记事本中写入下面两行代码，使用自己的大模型API KEY替换YOUR_KEY，目前项目使用deepseek、longcat模型

MY_DEEPSEEK_API_KEY = YOUR_KEY

MY_LONGCAT_API_KEY = YOUR_KEY

把创建的文件重命名为.env, **注意不要保留记事本的扩展名.txt**

2、config.py文件中的全局变量说明

'''

    # 是否打开学生端声音播发功能
    IS_SOUND_ON = True

    # 是否运行大模型评分
    IS_LLM_RUN = True
    #IS_LLM_RUN = False

    # 打开使用哪个大模型
    USING_DEEPSEEK = False
    USING_LONGCAT = True

'''

