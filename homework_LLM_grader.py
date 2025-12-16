# homework_LLM_grader.py
import requests
import time
from typing import Dict, List
from config import Config
import Promptconfig

class PythonCodeGrader:
    """Python程序自动判分助手"""

    #def __init__(self, homework_id, question_id):
    def __init__(self):
        self.api_key = Config.MY_LLM_API_KEY
        self.api_url = Config.MY_LLM_API_URL
        self.model = Config.MODEL_NAME
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        # 系统提示词 - 定义评分标准
        #self.system_prompt = Promptconfig.get_system_prompt(homework_id,question_id)
        self.system_prompt = Promptconfig.SYSTEM_PROMPT

    def evaluate_code(self, student_code: str, requirements: str, max_retries: int = 3) -> str:
        """
        评估Python代码

        Args:
            student_code: 学生提交的代码
            requirements: 题目要求
            max_retries: 最大重试次数

        Returns:
            评分结果字符串
        """
        user_prompt = f"""
        {requirements}
        {student_code}
        请根据评分标准进行客观评价。"""

        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": Config.TEMPERATURE,
            "max_tokens": 2000
        }

        for attempt in range(max_retries):
            try:
                print(f"🔍 正在评估代码 (尝试 {attempt + 1}/{max_retries})...")

                response = requests.post(
                    self.api_url,
                    headers=self.headers,
                    json=data,
                    timeout=Config.TIMEOUT
                )
                response.raise_for_status()

                result = response.json()
                evaluation = result['choices'][0]['message']['content']

                print("✅ LLM评估完成！")
                return evaluation

            except requests.exceptions.Timeout:
                print(f"⏰ 请求超时，正在重试... ({attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(2)  # 等待2秒后重试
                else:
                    return "❌ 评分失败：请求超时，请稍后重试"

            except requests.exceptions.RequestException as e:
                return f"❌ 网络错误：{str(e)}"

            except KeyError as e:
                return f"❌ API响应格式错误：{str(e)}"

            except Exception as e:
                return f"❌ 未知错误：{str(e)}"

        return "❌ 评分失败：达到最大重试次数"

    def evaluate_code_2(self, homework_content: str, max_retries: int = 3) -> str:
        """
        评估Python代码

        Args:
            student_code: 学生提交的代码
            requirements: 题目要求
            max_retries: 最大重试次数

        Returns:
            评分结果字符串
        """
        user_prompt = f"""
        {homework_content}
        请根据评分标准进行客观评价。"""

        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": Config.TEMPERATURE,
            "max_tokens": 2000
        }

        for attempt in range(max_retries):
            try:
                print(f"🔍 正在评估代码 (尝试 {attempt + 1}/{max_retries})...")

                response = requests.post(
                    self.api_url,
                    headers=self.headers,
                    json=data,
                    timeout=Config.TIMEOUT
                )
                response.raise_for_status()

                result = response.json()
                evaluation = result['choices'][0]['message']['content']

                print("✅ LLM评估完成！")
                return evaluation

            except requests.exceptions.Timeout:
                print(f"⏰ 请求超时，正在重试... ({attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(2)  # 等待2秒后重试
                else:
                    return "❌ 评分失败：请求超时，请稍后重试"

            except requests.exceptions.RequestException as e:
                return f"❌ 网络错误：{str(e)}"

            except KeyError as e:
                return f"❌ API响应格式错误：{str(e)}"

            except Exception as e:
                return f"❌ 未知错误：{str(e)}"

        return "❌ 评分失败：达到最大重试次数"

    #学习计划生成
    def generate_study_plan(self, homework_content: str, evaluation_result: str, max_retries: int = 3) -> str:
        """
        基于作业内容和评分结果生成个性化学习计划
        Args:
            homework_content: 作业内容
            evaluation_result: AI评分结果
            max_retries: 最大重试次数
        Returns:
            学习计划字符串
        """
        # 学习计划专属Prompt（适配Python作业场景）
        user_prompt = f"""
        请基于以下Python作业内容和AI评分结果，为学生制定学习计划：

        【作业内容】
        {homework_content[:1000]}  # 限制长度避免Prompt过长

        【AI评分结果】
        {evaluation_result[:10000]}  # 限制长度避免Prompt过长

        【学习计划要求】
        1. 结构：包含「学习目标」「核心内容」「练习任务」「薄弱点弥补」4部分
        2. 重点：针对评分中指出的错误/薄弱点制定弥补方案；
        3. 语言：中文，通俗易懂，符合Python初学者认知水平。
        """

        # 复用LLM API调用逻辑，仅替换Prompt
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是专业的Python编程学习规划师，擅长为学生制定可落地的学习计划。"},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": Config.TEMPERATURE,
            "max_tokens": 2000
        }

        for attempt in range(max_retries):
            try:
                print(f"📚 正在生成学习计划 (尝试 {attempt + 1}/{max_retries})...")
                response = requests.post(
                    self.api_url,
                    headers=self.headers,
                    json=data,
                    timeout=Config.TIMEOUT
                )
                response.raise_for_status()
                result = response.json()
                study_plan = result['choices'][0]['message']['content']
                print("✅ 学习计划生成完成！")
                return study_plan

            except requests.exceptions.Timeout:
                print(f"⏰ 请求超时，正在重试... ({attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    return "❌ 学习计划生成失败：请求超时，请稍后重试"

            except requests.exceptions.RequestException as e:
                return f"❌ 学习计划生成失败：网络错误 - {str(e)}"

            except KeyError as e:
                return f"❌ 学习计划生成失败：API响应格式错误 - {str(e)}"

            except Exception as e:
                return f"❌ 学习计划生成失败：未知错误 - {str(e)}"

        return "❌ 学习计划生成失败：达到最大重试次数"
    def batch_evaluate(self, submissions: List[Dict]) -> Dict:
        """
        批量评估多个代码提交

        Args:
            submissions: 提交列表，每个元素包含 'code' 和 'requirements'

        Returns:
            评估结果字典
        """
        results = {}

        for i, submission in enumerate(submissions, 1):
            print(f"\n📝 正在评估第 {i}/{len(submissions)} 个提交...")

            evaluation = self.evaluate_code(
                submission['code'],
                submission['requirements']
            )

            results[f"submission_{i}"] = {
                'code': submission['code'],
                'requirements': submission['requirements'],
                'evaluation': evaluation
            }

            # 添加延迟避免API限制
            time.sleep(1)

        return results

def main():
    """主函数 - 演示使用方法"""
    print("🐍 Python程序判分助手")
    print("=" * 50)
    try:
        # 创建判分器实例
        grader = PythonCodeGrader()

        # 示例1：单个代码评估
        print("\n1. 单个代码评估示例：")

        # 测试用例1 - 递归阶乘
        test_code_1 = """
        def factorial(n):
            if n == 0:
                return 1
            else:
                return n * factorial(n-1)
        测试
        print(factorial(5))"""

        requirements_1 = "编写一个计算阶乘的递归函数，能够处理正整数输入"

        result_1 = grader.evaluate_code(test_code_1, requirements_1)
        print("\n📊 评估结果：")
        print(result_1)
        print("=" * 50)
        '''
        # 测试用例2 - 有问题的代码
        test_code_2 = """
        def find_max(numbers):
            max_num = 0
            for num in numbers:
                if num > max_num:
                    max_num = num
            return max_num
        """
        requirements_2 = "编写一个函数，找出列表中的最大值，要求能处理负数和空列表"

        result_2 = grader.evaluate_code(test_code_2, requirements_2)
        print("\n📊 评估结果：")
        print(result_2)
        print("=" * 50)

        # 示例2：批量评估
        print("\n2. 批量评估示例：")

        submissions = [
            {
                'code': """                
                def is_prime(n):
                    if n < 2:
                        return False
                    for i in range(2, n):
                        if n % i == 0:
                            return False
                        return True""",
                'requirements': "编写一个判断素数的函数，要求优化性能"
            },
            {
                'code': """
                def count_vowels(string):
                    count = 0
                    for char in string:
                        if char in 'aeiouAEIOU':
                            count += 1
                    return count
                """,
                'requirements': "编写一个函数，统计字符串中元音字母的个数"
            },
            {
                'code': """
                def is_palindrome(string):
                    return string == string[::-1]
                """,
                'requirements': "编写一个函数，判断字符串是否是回文"
            },
            {
                'code': """
                def factorial(n):
                    if n == 0:
                        return 1
                    else:
                        return n * factorial(n-1)
                """,
                'requirements': "编写一个计算阶乘的函数"
            }
            ]

        batch_results = grader.batch_evaluate(submissions)

        print("\n📦 批量评估完成！")
        for key, result in batch_results.items():
            print(f"\n{key} 评估结果：")
            print(result['evaluation'])
            print("-" * 30)
        '''
    except ValueError as e:
        print(f"❌ 初始化错误：{e}")
    except Exception as e:
        print(f"❌ 运行错误：{e}")
    try:
        grader = PythonCodeGrader()
        # 测试学习计划生成
        test_code = """
            def factorial(n):
                if n == 0:
                    return 1
                else:
                    return n * factorial(n-1)
            print(factorial(5))
            """
        test_evaluation = "评分：90分。优点：递归逻辑正确，能处理正整数输入；不足：未做输入校验，未处理负数/非整数情况。"
        study_plan = grader.generate_study_plan(test_code, test_evaluation)
        print("\n📚 学习计划示例：")
        print(study_plan)
    except Exception as e:
        print(f"❌ 运行错误：{e}")

if __name__ == "__main__":
    main()

